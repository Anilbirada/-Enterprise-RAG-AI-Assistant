import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.chunk import ChunkSearchResult
from app.schemas.search import SemanticSearchRequest, HybridSearchRequest
from app.services.hybrid_search_service import HybridSearchService


def make_chunk(chunk_id: uuid.UUID, index: int, content: str, score: float = 0.5) -> ChunkSearchResult:
    return ChunkSearchResult(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        chunk_index=index,
        content=content,
        token_count=10,
        score=score,
    )


def test_rrf_both_channels_boosts_overlapping_chunk():
    """Test that a chunk appearing in both dense and sparse channels scores higher than single-channel chunks."""
    cid_both = uuid.uuid4()
    cid_dense_only = uuid.uuid4()
    cid_sparse_only = uuid.uuid4()

    # Dense ranking: [cid_both (rank 1), cid_dense_only (rank 2)]
    dense_results = [
        make_chunk(cid_both, 0, "Both channels content", score=0.9),
        make_chunk(cid_dense_only, 1, "Dense only content", score=0.85),
    ]

    # Sparse ranking: [cid_both (rank 1), cid_sparse_only (rank 2)]
    sparse_results = [
        make_chunk(cid_both, 0, "Both channels content", score=15.0),
        make_chunk(cid_sparse_only, 2, "Sparse only content", score=12.0),
    ]

    fused = HybridSearchService.compute_reciprocal_rank_fusion(
        dense_results=dense_results,
        sparse_results=sparse_results,
        dense_weight=0.7,
        sparse_weight=0.3,
        k=60,
        limit=10,
    )

    assert len(fused) == 3
    # Top result MUST be the overlapping chunk
    assert fused[0].chunk_id == cid_both
    # Expected score: (0.7 / 61) + (0.3 / 61) = 1.0 / 61 = 0.016393
    expected_score = round((0.7 / 61.0) + (0.3 / 61.0), 6)
    assert abs(fused[0].score - expected_score) < 1e-5

    # Second result should be dense-only (weight 0.7 > 0.3)
    assert fused[1].chunk_id == cid_dense_only
    # Third result should be sparse-only
    assert fused[2].chunk_id == cid_sparse_only


def test_rrf_empty_lists():
    """Test RRF when one or both result lists are empty."""
    cid = uuid.uuid4()
    dense_chunk = make_chunk(cid, 0, "Dense chunk", score=0.8)

    # Empty sparse
    res1 = HybridSearchService.compute_reciprocal_rank_fusion(
        dense_results=[dense_chunk],
        sparse_results=[],
        dense_weight=0.7,
        sparse_weight=0.3,
        k=60,
        limit=10,
    )
    assert len(res1) == 1
    assert res1[0].chunk_id == cid
    assert abs(res1[0].score - round(0.7 / 61.0, 6)) < 1e-5

    # Empty dense
    sparse_chunk = make_chunk(cid, 0, "Sparse chunk", score=5.0)
    res2 = HybridSearchService.compute_reciprocal_rank_fusion(
        dense_results=[],
        sparse_results=[sparse_chunk],
        dense_weight=0.7,
        sparse_weight=0.3,
        k=60,
        limit=10,
    )
    assert len(res2) == 1
    assert res2[0].chunk_id == cid
    assert abs(res2[0].score - round(0.3 / 61.0, 6)) < 1e-5

    # Both empty
    res3 = HybridSearchService.compute_reciprocal_rank_fusion(
        dense_results=[],
        sparse_results=[],
    )
    assert res3 == []


def test_rrf_limit_truncation():
    """Test that RRF output respects the limit parameter."""
    dense = [make_chunk(uuid.uuid4(), i, f"Chunk {i}") for i in range(10)]
    fused = HybridSearchService.compute_reciprocal_rank_fusion(
        dense_results=dense,
        sparse_results=[],
        limit=4,
    )
    assert len(fused) == 4


@pytest.mark.asyncio
async def test_search_semantic_no_matching_document_filter():
    """Test semantic search returns empty SearchResponse immediately if document filter yields 0 docs."""
    service = HybridSearchService()
    mock_session = AsyncMock()

    # Mock _resolve_allowed_document_ids returning empty list
    service._resolve_allowed_document_ids = AsyncMock(return_value=[])

    req = SemanticSearchRequest(
        query="Enterprise security",
        document_ids=[uuid.uuid4()],
    )

    resp = await service.search_semantic(
        session=mock_session,
        organization_id=uuid.uuid4(),
        request=req,
    )

    assert resp.total_candidates == 0
    assert resp.results == []
    assert resp.retrieval_method == "DENSE"
