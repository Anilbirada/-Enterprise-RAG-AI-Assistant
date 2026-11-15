import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.search import (
    HybridSearchRequest,
    SearchResponse,
    SemanticSearchRequest,
)
from app.services.hybrid_search_service import HybridSearchService

logger = logging.getLogger("enterprise_rag.search_api")

router = APIRouter()


@router.post(
    "/semantic",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Dense Vector Semantic Search",
    description="Performs cosine similarity search using pgvector HNSW indexing on dense 1536d embeddings.",
)
async def semantic_search(
    request: SemanticSearchRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permission.VIEW_DOCUMENTS)),
) -> SearchResponse:
    """Executes dense vector similarity search scoped to current user's organization."""
    service = HybridSearchService()
    return await service.search_semantic(
        session=session,
        organization_id=current_user.organization_id,
        request=request,
    )


@router.post(
    "/hybrid",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Hybrid Retrieval (Dense + Sparse with RRF)",
    description="Combines dense vector cosine similarity and sparse full-text lexical search using Reciprocal Rank Fusion.",
)
async def hybrid_search(
    request: HybridSearchRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(Permission.VIEW_DOCUMENTS)),
) -> SearchResponse:
    """Executes hybrid retrieval combining dense and sparse search with RRF scoped to tenant."""
    service = HybridSearchService()
    return await service.search_hybrid(
        session=session,
        organization_id=current_user.organization_id,
        request=request,
    )
