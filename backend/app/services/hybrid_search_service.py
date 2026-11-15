import logging
import time
import uuid
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.models.document import Document
from app.repositories.vector_repository import VectorRepository
from app.schemas.chunk import ChunkSearchResult
from app.schemas.search import (
    HybridSearchRequest,
    SearchResponse,
    SemanticSearchRequest,
)
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger("enterprise_rag.hybrid_search_service")


class HybridSearchService:
    """Service providing dense semantic search, sparse full-text search, and Reciprocal Rank Fusion."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        vector_repository: Optional[VectorRepository] = None,
    ) -> None:
        self.embedder = embedding_service or EmbeddingService()
        self.vector_repo = vector_repository or VectorRepository()

    async def _resolve_allowed_document_ids(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        department_id: Optional[uuid.UUID] = None,
        requested_doc_ids: Optional[List[uuid.UUID]] = None,
    ) -> Optional[List[uuid.UUID]]:
        """Resolves active document IDs scoped by tenant and optional department filter."""
        if not department_id and not requested_doc_ids:
            return None

        stmt = select(Document.id).where(
            Document.organization_id == organization_id,
            Document.status == "COMPLETED",
        )

        if department_id:
            stmt = stmt.where(Document.department_id == department_id)

        if requested_doc_ids:
            stmt = stmt.where(Document.id.in_(requested_doc_ids))

        result = await session.execute(stmt)
        allowed_ids = list(result.scalars().all())

        if not allowed_ids:
            # If filters were supplied but matched nothing, return empty list to enforce empty search result
            return []

        return allowed_ids

    @staticmethod
    def compute_reciprocal_rank_fusion(
        dense_results: List[ChunkSearchResult],
        sparse_results: List[ChunkSearchResult],
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
        k: int = 60,
        limit: int = 10,
    ) -> List[ChunkSearchResult]:
        """Merges dense and sparse result lists using weighted Reciprocal Rank Fusion (RRF).

        Formula:
            RRF_Score(d) = (dense_weight / (k + rank_dense(d))) + (sparse_weight / (k + rank_sparse(d)))
        """
        rrf_scores: Dict[uuid.UUID, float] = {}
        chunk_map: Dict[uuid.UUID, ChunkSearchResult] = {}

        # 1. Process dense rankings (1-based rank: 1, 2, 3...)
        for rank, chunk in enumerate(dense_results, start=1):
            chunk_id = chunk.chunk_id
            chunk_map[chunk_id] = chunk
            dense_contribution = dense_weight / (k + rank)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + dense_contribution

        # 2. Process sparse rankings (1-based rank: 1, 2, 3...)
        for rank, chunk in enumerate(sparse_results, start=1):
            chunk_id = chunk.chunk_id
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = chunk
            sparse_contribution = sparse_weight / (k + rank)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + sparse_contribution

        # 3. Sort chunks by fused RRF score descending
        sorted_chunk_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True,
        )

        # 4. Construct final results with RRF scores
        fused_results: List[ChunkSearchResult] = []
        for cid in sorted_chunk_ids[:limit]:
            base_chunk = chunk_map[cid]
            # Copy chunk with updated fused score and tracking metadata
            fused_chunk = base_chunk.model_copy()
            fused_chunk.score = round(rrf_scores[cid], 6)
            fused_chunk.metadata = {
                **base_chunk.metadata,
                "fusion_method": "RRF",
                "rrf_score": fused_chunk.score,
            }
            fused_results.append(fused_chunk)

        return fused_results

    async def search_semantic(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        request: SemanticSearchRequest,
    ) -> SearchResponse:
        """Executes dense vector similarity search with query embedding generation."""
        start_time = time.perf_counter()

        # 1. Resolve document filters
        allowed_doc_ids = await self._resolve_allowed_document_ids(
            session=session,
            organization_id=organization_id,
            department_id=request.department_id,
            requested_doc_ids=request.document_ids,
        )

        if allowed_doc_ids == []:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return SearchResponse(
                query=request.query,
                retrieval_method="DENSE",
                total_candidates=0,
                execution_time_ms=round(elapsed_ms, 2),
                results=[],
            )

        # 2. Generate dense query embedding vector (1536d)
        embed_res = await self.embedder.generate_embeddings_for_texts([request.query])
        if not embed_res.embeddings:
            raise ValidationException("Failed to generate embedding vector for search query.")
        query_vector = embed_res.embeddings[0]

        # 3. Query pgvector HNSW index
        results = await self.vector_repo.search_vector_similarity(
            session=session,
            organization_id=organization_id,
            query_embedding=query_vector,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold,
            filter_document_ids=allowed_doc_ids,
            active_only=True,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SearchResponse(
            query=request.query,
            retrieval_method="DENSE",
            total_candidates=len(results),
            execution_time_ms=round(elapsed_ms, 2),
            results=results,
        )

    async def search_hybrid(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        request: HybridSearchRequest,
    ) -> SearchResponse:
        """Executes hybrid retrieval combining dense cosine similarity and sparse full-text search with RRF."""
        start_time = time.perf_counter()

        # 1. Resolve document filters
        allowed_doc_ids = await self._resolve_allowed_document_ids(
            session=session,
            organization_id=organization_id,
            department_id=request.department_id,
            requested_doc_ids=request.document_ids,
        )

        if allowed_doc_ids == []:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return SearchResponse(
                query=request.query,
                retrieval_method="HYBRID",
                total_candidates=0,
                execution_time_ms=round(elapsed_ms, 2),
                results=[],
            )

        # Fetch candidate pool (oversample by factor of 2 or minimum 20 to allow rich fusion)
        fetch_k = max(request.limit * 2, 20)

        # 2. Channel A: Dense Vector Retrieval
        embed_res = await self.embedder.generate_embeddings_for_texts([request.query])
        query_vector = embed_res.embeddings[0] if embed_res.embeddings else []

        dense_candidates: List[ChunkSearchResult] = []
        if query_vector and request.dense_weight > 0.0:
            dense_candidates = await self.vector_repo.search_vector_similarity(
                session=session,
                organization_id=organization_id,
                query_embedding=query_vector,
                limit=fetch_k,
                similarity_threshold=request.similarity_threshold,
                filter_document_ids=allowed_doc_ids,
                active_only=True,
            )

        # 3. Channel B: Sparse Full-Text Search (tsvector GIN)
        sparse_candidates: List[ChunkSearchResult] = []
        if request.sparse_weight > 0.0:
            sparse_candidates = await self.vector_repo.search_full_text(
                session=session,
                organization_id=organization_id,
                query_text=request.query,
                limit=fetch_k,
                filter_document_ids=allowed_doc_ids,
                active_only=True,
            )

        # 4. Channel Fusion: Reciprocal Rank Fusion
        fused_results = self.compute_reciprocal_rank_fusion(
            dense_results=dense_candidates,
            sparse_results=sparse_candidates,
            dense_weight=request.dense_weight,
            sparse_weight=request.sparse_weight,
            k=request.rrf_k,
            limit=request.limit,
        )

        total_unique_candidates = len(
            set([c.chunk_id for c in dense_candidates] + [c.chunk_id for c in sparse_candidates])
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info(
            f"Hybrid search executed for tenant {organization_id} in {elapsed_ms:.2f}ms: "
            f"{len(dense_candidates)} dense, {len(sparse_candidates)} sparse candidates "
            f"merged into {len(fused_results)} results."
        )

        return SearchResponse(
            query=request.query,
            retrieval_method="HYBRID",
            total_candidates=total_unique_candidates,
            execution_time_ms=round(elapsed_ms, 2),
            results=fused_results,
        )
