from datetime import datetime, timezone
import logging
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.repositories.vector_repository import VectorRepository
from app.schemas.chunk import ChunkingStatistics, DocumentChunkData
from app.schemas.extraction import ExtractedDocument
from app.services.chunking_service import ChunkingService
from app.services.document_extraction_service import DocumentExtractionService
from app.services.embedding_service import EmbeddingService
from app.services.storage.base import StorageProvider

logger = logging.getLogger("enterprise_rag.chunking_embedding_pipeline")


class ChunkingAndEmbeddingPipeline:
    """Orchestrates token-aware chunking and batch vector embedding generation."""

    def __init__(
        self,
        chunking_service: Optional[ChunkingService] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> None:
        self.chunker = chunking_service or ChunkingService()
        self.embedder = embedding_service or EmbeddingService()

    async def execute_pipeline(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        storage_provider: StorageProvider,
        extracted_doc: Optional[ExtractedDocument] = None,
        persist_chunks: bool = False,
    ) -> Tuple[List[DocumentChunkData], ChunkingStatistics]:
        """Executes full chunking, embedding, and progress tracking lifecycle."""
        # 1. Fetch Document and active Job
        stmt = (
            select(Document)
            .options(selectinload(Document.ingestion_jobs))
            .where(Document.id == document_id)
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise EntityNotFoundException("Document", document_id)

        job = None
        if doc.ingestion_jobs:
            job = sorted(doc.ingestion_jobs, key=lambda j: j.created_at, reverse=True)[0]

        try:
            # 2. Extract content if not already provided
            if not extracted_doc:
                extracted_doc = await DocumentExtractionService.process_document_extraction(
                    session=session,
                    document_id=document_id,
                    storage_provider=storage_provider,
                )

            # 3. Transition to CHUNKING
            doc.status = "CHUNKING"
            if job:
                job.status = "CHUNKING"
                job.progress_percent = 35
            await session.commit()
            logger.info(f"Document '{doc.id}' status transitioned to CHUNKING.")

            # 4. Perform token-aware recursive chunking
            chunks = self.chunker.chunk_document(
                document=extracted_doc,
                organization_id=doc.organization_id,
                document_id=doc.id,
                version_id=doc.current_version_id,
            )
            stats = self.chunker.calculate_statistics(chunks)

            # 5. Transition to EMBEDDING
            doc.status = "EMBEDDING"
            if job:
                job.status = "EMBEDDING"
                job.progress_percent = 50
            await session.commit()
            logger.info(f"Document '{doc.id}' status transitioned to EMBEDDING.")

            # 6. Generate 1536d vector embeddings
            embedded_chunks = await self.embedder.embed_chunks(chunks)

            # Record chunking and embedding metadata on document
            doc_metadata = dict(doc.metadata_ or {})
            doc_metadata.update({
                "chunk_count": stats.total_chunks,
                "total_tokens": stats.total_tokens,
                "avg_chunk_tokens": stats.average_tokens_per_chunk,
                "chunks_with_tables": stats.chunks_with_tables,
                "embedding_model": self.embedder.model,
                "embedding_dimension": self.embedder.dimensions,
            })
            doc.metadata_ = doc_metadata
            doc.error_message = None

            if job:
                job.progress_percent = 75

            if persist_chunks:
                # 7. Persist chunks and 1536d vectors into PostgreSQL pgvector
                await VectorRepository.batch_insert_chunks(
                    session=session,
                    chunks=embedded_chunks,
                    is_active=True,
                )
                doc.status = "COMPLETED"
                if job:
                    job.status = "COMPLETED"
                    job.progress_percent = 100
                    job.completed_at = datetime.now(timezone.utc)

            await session.commit()
            logger.info(
                f"Successfully generated embeddings for {len(embedded_chunks)} chunks of document '{doc.id}'."
            )
            return embedded_chunks, stats

        except Exception as exc:
            logger.error(f"Chunking/Embedding pipeline failed for document '{doc.id}': {exc}", exc_info=True)
            doc.status = "FAILED"
            doc.error_message = str(exc)
            if job:
                job.status = "FAILED"
                job.error_message = str(exc)
            await session.commit()
            raise
