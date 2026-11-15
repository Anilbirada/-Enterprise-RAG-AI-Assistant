import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.models.document_chunk import DocumentChunk
from app.schemas.chunk import ChunkSearchResult, DocumentChunkData

logger = logging.getLogger("enterprise_rag.vector_repository")


class VectorRepository:
    """Repository handling pgvector vector similarity and tsvector full-text search persistence."""

    @staticmethod
    async def batch_insert_chunks(
        session: AsyncSession,
        chunks: List[DocumentChunkData],
        is_active: bool = True,
    ) -> List[DocumentChunk]:
        """Persists a list of document chunks and their 1536d vector embeddings in PostgreSQL."""
        if not chunks:
            return []

        orm_chunks: List[DocumentChunk] = []
        for chunk_data in chunks:
            if not chunk_data.embedding:
                raise ValidationException(
                    f"Cannot persist chunk {chunk_data.metadata.chunk_index}: embedding vector is missing."
                )

            if len(chunk_data.embedding) != 1536:
                raise ValidationException(
                    f"Cannot persist chunk {chunk_data.metadata.chunk_index}: "
                    f"embedding dimension must be 1536, got {len(chunk_data.embedding)}."
                )

            chunk_meta = {
                "page_number": chunk_data.metadata.page_number,
                "char_count": chunk_data.metadata.char_count,
                "has_table": chunk_data.metadata.has_table,
                "section_title": chunk_data.metadata.section_title,
                **chunk_data.metadata.extra,
            }

            orm_chunk = DocumentChunk(
                id=uuid.uuid4(),
                organization_id=chunk_data.metadata.organization_id,
                document_id=chunk_data.metadata.document_id,
                version_id=chunk_data.metadata.version_id,
                chunk_index=chunk_data.metadata.chunk_index,
                content=chunk_data.content,
                token_count=chunk_data.metadata.token_count,
                is_active=is_active,
                embedding=chunk_data.embedding,
                metadata_=chunk_meta,
            )
            orm_chunks.append(orm_chunk)

        session.add_all(orm_chunks)
        await session.flush()
        logger.info(
            f"Successfully stored {len(orm_chunks)} chunks for document {chunks[0].metadata.document_id} "
            f"(version {chunks[0].metadata.version_id}, tenant {chunks[0].metadata.organization_id})."
        )
        return orm_chunks

    @staticmethod
    async def get_chunks_by_document(
        session: AsyncSession,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        active_only: bool = True,
    ) -> List[DocumentChunk]:
        """Retrieves all chunks belonging to a document ordered by chunk_index."""
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.document_id == document_id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        if active_only:
            stmt = stmt.where(DocumentChunk.is_active.is_(True))

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_chunks_by_version(
        session: AsyncSession,
        organization_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> List[DocumentChunk]:
        """Retrieves all chunks for a specific document version."""
        stmt = (
            select(DocumentChunk)
            .where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.version_id == version_id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def deactivate_chunks_by_version(
        session: AsyncSession,
        organization_id: uuid.UUID,
        version_id: uuid.UUID,
    ) -> int:
        """Deactivates all chunks associated with a specific version (e.g. when superseded)."""
        stmt = (
            update(DocumentChunk)
            .where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.version_id == version_id,
            )
            .values(is_active=False)
        )
        result = await session.execute(stmt)
        logger.info(f"Deactivated {result.rowcount} chunks for version {version_id}.")
        return result.rowcount or 0

    @staticmethod
    async def delete_chunks_by_document(
        session: AsyncSession,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> int:
        """Permanently deletes all chunks for a document."""
        stmt = delete(DocumentChunk).where(
            DocumentChunk.organization_id == organization_id,
            DocumentChunk.document_id == document_id,
        )
        result = await session.execute(stmt)
        logger.info(f"Deleted {result.rowcount} chunks for document {document_id}.")
        return result.rowcount or 0

    @staticmethod
    async def search_vector_similarity(
        session: AsyncSession,
        organization_id: uuid.UUID,
        query_embedding: List[float],
        limit: int = 10,
        similarity_threshold: float = 0.0,
        filter_document_ids: Optional[List[uuid.UUID]] = None,
        active_only: bool = True,
    ) -> List[ChunkSearchResult]:
        """Performs tenant-filtered vector cosine similarity search using pgvector's <=> operator."""
        if not query_embedding or len(query_embedding) != 1536:
            raise ValidationException(
                f"Query embedding dimension mismatch: expected 1536, got {len(query_embedding) if query_embedding else 0}."
            )

        # Distance is cosine distance (1 - cosine_similarity).
        # Cosine similarity score = 1.0 - distance
        cosine_distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        similarity_expr = (1.0 - cosine_distance).label("similarity")

        stmt = (
            select(
                DocumentChunk,
                similarity_expr,
            )
            .where(
                DocumentChunk.organization_id == organization_id,
            )
        )

        if active_only:
            stmt = stmt.where(DocumentChunk.is_active.is_(True))

        if filter_document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(filter_document_ids))

        if similarity_threshold > 0.0:
            stmt = stmt.where(similarity_expr >= similarity_threshold)

        stmt = stmt.order_by(cosine_distance.asc()).limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        results: List[ChunkSearchResult] = []
        for chunk, score in rows:
            meta = dict(chunk.metadata_ or {})
            results.append(
                ChunkSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    organization_id=chunk.organization_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    score=float(score),
                    page_number=meta.get("page_number"),
                    section_title=meta.get("section_title"),
                    has_table=meta.get("has_table", False),
                    metadata=meta,
                )
            )

        return results

    @staticmethod
    async def search_full_text(
        session: AsyncSession,
        organization_id: uuid.UUID,
        query_text: str,
        limit: int = 10,
        filter_document_ids: Optional[List[uuid.UUID]] = None,
        active_only: bool = True,
    ) -> List[ChunkSearchResult]:
        """Performs tenant-filtered full-text search against the generated search_vector (GIN indexed)."""
        clean_query = query_text.strip()
        if not clean_query:
            return []

        ts_query = func.plainto_tsquery("english", clean_query)
        rank_expr = func.ts_rank_cd(DocumentChunk.search_vector, ts_query).label("rank")

        stmt = (
            select(
                DocumentChunk,
                rank_expr,
            )
            .where(
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.search_vector.op("@@")(ts_query),
            )
        )

        if active_only:
            stmt = stmt.where(DocumentChunk.is_active.is_(True))

        if filter_document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(filter_document_ids))

        stmt = stmt.order_by(rank_expr.desc()).limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

        results: List[ChunkSearchResult] = []
        for chunk, rank in rows:
            meta = dict(chunk.metadata_ or {})
            results.append(
                ChunkSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    organization_id=chunk.organization_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    score=float(rank),
                    page_number=meta.get("page_number"),
                    section_title=meta.get("section_title"),
                    has_table=meta.get("has_table", False),
                    metadata=meta,
                )
            )

        return results
