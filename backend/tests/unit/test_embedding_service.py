import math
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from openai import RateLimitError, APIConnectionError, InternalServerError

from app.core.exceptions import ExternalServiceException, ValidationException
from app.schemas.chunk import DocumentChunkData, ChunkMetadata
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def mock_embedding_service():
    """Provides an EmbeddingService configured without an API key (mock mode)."""
    return EmbeddingService(
        api_key=None,
        model="text-embedding-3-small",
        dimensions=1536,
        batch_size=5,
        max_retries=3,
    )


def test_mock_vector_generation(mock_embedding_service):
    """Test deterministic 1536-dimensional mock vector generation."""
    text1 = "Antigravity Enterprise RAG Architecture"
    vec1 = mock_embedding_service._generate_mock_vector(text1)
    
    # 1. Exact length
    assert len(vec1) == 1536
    
    # 2. Unit norm (L2 norm should be ~1.0)
    norm = math.sqrt(sum(v * v for v in vec1))
    assert abs(norm - 1.0) < 1e-5
    
    # 3. Determinism
    vec1_repeat = mock_embedding_service._generate_mock_vector(text1)
    assert vec1 == vec1_repeat
    
    # 4. Distinct text produces distinct vectors
    vec2 = mock_embedding_service._generate_mock_vector("Different text content")
    assert vec1 != vec2


def test_vector_validation_success(mock_embedding_service):
    """Test validation passes for a valid 1536d vector."""
    valid_vec = [0.1] * 1536
    # Should not raise
    mock_embedding_service.validate_vector(valid_vec, chunk_index=0)


def test_vector_validation_failures(mock_embedding_service):
    """Test validation fails for wrong dimension, NaN, or Inf values."""
    # Wrong dimension
    with pytest.raises(ValidationException, match="dimension mismatch"):
        mock_embedding_service.validate_vector([0.1] * 512, chunk_index=0)

    # Empty vector
    with pytest.raises(ValidationException, match="dimension mismatch"):
        mock_embedding_service.validate_vector([], chunk_index=0)

    # NaN value
    nan_vec = [0.1] * 1536
    nan_vec[42] = float("nan")
    with pytest.raises(ValidationException, match="NaN or Inf"):
        mock_embedding_service.validate_vector(nan_vec, chunk_index=1)

    # Inf value
    inf_vec = [0.1] * 1536
    inf_vec[100] = float("inf")
    with pytest.raises(ValidationException, match="NaN or Inf"):
        mock_embedding_service.validate_vector(inf_vec, chunk_index=2)


@pytest.mark.asyncio
async def test_generate_embeddings_empty(mock_embedding_service):
    """Test that empty input yields empty output."""
    result = await mock_embedding_service.generate_embeddings_for_texts([])
    assert result.embeddings == []
    assert result.total_tokens_consumed == 0
    assert result.dimension == 1536


@pytest.mark.asyncio
async def test_generate_embeddings_batching(mock_embedding_service):
    """Test batching splits texts into chunks respecting batch_size."""
    service = EmbeddingService(
        api_key=None,
        dimensions=1536,
        batch_size=2,
    )
    texts = [f"Text chunk number {i}" for i in range(5)]
    result = await service.generate_embeddings_for_texts(texts)

    assert len(result.embeddings) == 5
    for vec in result.embeddings:
        assert len(vec) == 1536


@pytest.mark.asyncio
async def test_embed_chunks(mock_embedding_service):
    """Test embedding enrichment on DocumentChunkData objects."""
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    chunks = [
        DocumentChunkData(
            content=f"Chunk content {i}",
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org_id,
                chunk_index=i,
                page_number=1,
                token_count=10,
                char_count=15,
                start_char=0,
                end_char=15,
            ),
        )
        for i in range(3)
    ]

    for c in chunks:
        assert c.embedding is None

    enriched_chunks = await mock_embedding_service.embed_chunks(chunks)

    assert len(enriched_chunks) == 3
    for c in enriched_chunks:
        assert c.embedding is not None
        assert len(c.embedding) == 1536


@pytest.mark.asyncio
async def test_retry_on_rate_limit_error():
    """Test retry behavior when OpenAI API raises a transient RateLimitError."""
    service = EmbeddingService(
        api_key="sk-fake-key",
        model="text-embedding-3-small",
        dimensions=1536,
        batch_size=10,
        max_retries=3,
    )

    mock_response = MagicMock()
    mock_item = MagicMock()
    mock_item.embedding = [0.05] * 1536
    mock_response.data = [mock_item]
    mock_response.usage.total_tokens = 25

    # Mock client to fail once with RateLimitError, then succeed
    mock_client = MagicMock()
    mock_create = AsyncMock()
    rate_limit_err = RateLimitError(
        message="Rate limit exceeded",
        response=MagicMock(status_code=429),
        body={"error": {"message": "Rate limit exceeded"}},
    )
    mock_create.side_effect = [rate_limit_err, mock_response]
    mock_client.embeddings.create = mock_create
    service.client = mock_client

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        embeddings, tokens = await service._embed_batch_with_retry(["Sample query"])
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 1536
        assert tokens == 25
        assert mock_create.call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_max_retries_exceeded():
    """Test that exceeding max retries raises ExternalServiceException."""
    service = EmbeddingService(
        api_key="sk-fake-key",
        model="text-embedding-3-small",
        dimensions=1536,
        batch_size=10,
        max_retries=2,
    )

    mock_client = MagicMock()
    mock_create = AsyncMock()
    conn_err = APIConnectionError(request=MagicMock())
    mock_create.side_effect = conn_err
    mock_client.embeddings.create = mock_create
    service.client = mock_client

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ExternalServiceException, match="OpenAI Embeddings API"):
            await service._embed_batch_with_retry(["Sample query"])

    assert mock_create.call_count == 2
