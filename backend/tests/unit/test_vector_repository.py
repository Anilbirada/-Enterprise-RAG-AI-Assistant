import uuid
import pytest
from unittest.mock import AsyncMock

from app.core.exceptions import ValidationException
from app.repositories.vector_repository import VectorRepository
from app.schemas.chunk import ChunkMetadata, DocumentChunkData


@pytest.mark.asyncio
async def test_batch_insert_missing_embedding():
    """Test batch_insert_chunks rejects chunks without embedding vectors."""
    mock_session = AsyncMock()
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    chunk_without_vec = DocumentChunkData(
        content="Sample chunk without vector",
        metadata=ChunkMetadata(
            document_id=doc_id,
            version_id=ver_id,
            organization_id=org_id,
            chunk_index=0,
            token_count=10,
            char_count=26,
        ),
        embedding=None,
    )

    with pytest.raises(ValidationException, match="embedding vector is missing"):
        await VectorRepository.batch_insert_chunks(
            session=mock_session,
            chunks=[chunk_without_vec],
        )


@pytest.mark.asyncio
async def test_batch_insert_invalid_embedding_dimension():
    """Test batch_insert_chunks rejects chunks with wrong embedding dimension."""
    mock_session = AsyncMock()
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    chunk_bad_dim = DocumentChunkData(
        content="Sample chunk with 512d vector",
        metadata=ChunkMetadata(
            document_id=doc_id,
            version_id=ver_id,
            organization_id=org_id,
            chunk_index=0,
            token_count=10,
            char_count=28,
        ),
        embedding=[0.1] * 512,  # Expected 1536
    )

    with pytest.raises(ValidationException, match="embedding dimension must be 1536"):
        await VectorRepository.batch_insert_chunks(
            session=mock_session,
            chunks=[chunk_bad_dim],
        )


@pytest.mark.asyncio
async def test_batch_insert_empty_list():
    """Test batch_insert_chunks handles empty list gracefully."""
    mock_session = AsyncMock()
    result = await VectorRepository.batch_insert_chunks(session=mock_session, chunks=[])
    assert result == []


@pytest.mark.asyncio
async def test_search_vector_similarity_invalid_query_dimension():
    """Test vector similarity search rejects queries with invalid dimensions."""
    mock_session = AsyncMock()
    org_id = uuid.uuid4()

    # None query
    with pytest.raises(ValidationException, match="expected 1536"):
        await VectorRepository.search_vector_similarity(
            session=mock_session,
            organization_id=org_id,
            query_embedding=[],
        )

    # 512d query
    with pytest.raises(ValidationException, match="expected 1536"):
        await VectorRepository.search_vector_similarity(
            session=mock_session,
            organization_id=org_id,
            query_embedding=[0.05] * 512,
        )


@pytest.mark.asyncio
async def test_search_full_text_empty_query():
    """Test full text search returns empty list on blank or whitespace query."""
    mock_session = AsyncMock()
    org_id = uuid.uuid4()

    res = await VectorRepository.search_full_text(
        session=mock_session,
        organization_id=org_id,
        query_text="   ",
    )
    assert res == []
