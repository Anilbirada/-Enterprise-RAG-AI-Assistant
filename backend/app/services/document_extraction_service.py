import logging
import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import EntityNotFoundException, ValidationException
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.schemas.extraction import ExtractedDocument
from app.services.extractors import get_document_extractor
from app.services.storage.base import StorageProvider

logger = logging.getLogger("enterprise_rag.document_extraction_service")


class DocumentExtractionService:
    """Service coordinating document extraction, status transitions, and error management."""

    @staticmethod
    async def extract_from_bytes(
        file_content: bytes,
        file_type: str,
        file_name: str,
        document_id: Optional[str] = None,
    ) -> ExtractedDocument:
        """Directly parses file bytes using the appropriate extractor."""
        extractor = get_document_extractor(file_type)
        return await extractor.extract(
            file_content=file_content,
            file_name=file_name,
            document_id=document_id,
        )

    @classmethod
    async def process_document_extraction(
        cls,
        session: AsyncSession,
        document_id: uuid.UUID,
        storage_provider: StorageProvider,
    ) -> ExtractedDocument:
        """Executes full document extraction lifecycle: reads from storage, updates status, and extracts content."""
        # 1. Fetch Document and IngestionJob
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

        # 2. Transition status to PARSING
        doc.status = "PARSING"
        if job:
            job.status = "PARSING"
        await session.commit()
        logger.info(f"Document '{doc.id}' status transitioned to PARSING.")

        # 3. Stream bytes from storage provider
        try:
            chunks = []
            async for chunk in storage_provider.get(doc.file_path):
                chunks.append(chunk)
            file_bytes = b"".join(chunks)

            # 4. Extract structured content
            extracted_doc = await cls.extract_from_bytes(
                file_content=file_bytes,
                file_type=doc.file_type,
                file_name=doc.file_name,
                document_id=str(doc.id),
            )

            # 5. Update document metadata with extraction statistics
            doc_metadata = dict(doc.metadata_ or {})
            doc_metadata.update({
                "page_count": extracted_doc.total_pages,
                "word_count": extracted_doc.total_words,
                "character_count": extracted_doc.total_characters,
                "table_count": extracted_doc.total_tables,
                "extracted_title": extracted_doc.metadata.get("title"),
            })
            doc.metadata_ = doc_metadata
            doc.error_message = None

            # Transition document to PARSING and record extraction progress on job
            if job:
                job.progress_percent = 25  # Extraction complete; awaiting chunking & embedding
            await session.commit()

            logger.info(
                f"Successfully extracted document '{doc.id}': "
                f"{extracted_doc.total_pages} pages, {extracted_doc.total_words} words, "
                f"{extracted_doc.total_tables} tables."
            )
            return extracted_doc

        except Exception as exc:
            logger.error(f"Extraction failed for document '{doc.id}': {exc}", exc_info=True)
            doc.status = "FAILED"
            doc.error_message = str(exc)
            if job:
                job.status = "FAILED"
                job.error_message = str(exc)
            await session.commit()
            raise
