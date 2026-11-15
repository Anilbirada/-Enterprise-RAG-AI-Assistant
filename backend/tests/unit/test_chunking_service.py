import uuid
import pytest
from app.schemas.extraction import ExtractedDocument, ExtractedPage
from app.services.chunking_service import ChunkingService


def test_chunking_service_token_counting():
    """Test exact token counting via tiktoken cl100k_base."""
    chunker = ChunkingService(chunk_size_tokens=100, chunk_overlap_tokens=20)
    text = "Hello world! This is a test of the tiktoken tokenizer."
    token_count = chunker.count_tokens(text)
    assert token_count > 5
    assert chunker.count_tokens("") == 0


def test_chunking_service_single_chunk_under_limit():
    """Test text smaller than chunk_size_tokens remains a single chunk."""
    chunker = ChunkingService(chunk_size_tokens=200, chunk_overlap_tokens=30)
    doc = ExtractedDocument(
        file_type="TXT",
        file_name="sample.txt",
        full_text="A brief corporate memorandum that easily fits into one chunk.",
        pages=[
            ExtractedPage(
                page_number=1,
                text="A brief corporate memorandum that easily fits into one chunk.",
                raw_text="A brief corporate memorandum that easily fits into one chunk.",
            )
        ],
    )
    chunks = chunker.chunk_document(
        document=doc,
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )
    assert len(chunks) == 1
    assert chunks[0].metadata.chunk_index == 0
    assert chunks[0].metadata.page_number == 1
    assert chunks[0].metadata.token_count <= 200


def test_chunking_service_recursive_splitting_with_overlap():
    """Test multi-paragraph text splitting with sliding window token overlap."""
    chunker = ChunkingService(chunk_size_tokens=40, chunk_overlap_tokens=10)
    
    # 5 distinct paragraphs
    paragraphs = [
        f"Paragraph {i}: Enterprise RAG systems require reliable chunking architectures with strict semantic boundaries."
        for i in range(1, 6)
    ]
    full_text = "\n\n".join(paragraphs)

    doc = ExtractedDocument(
        file_type="TXT",
        file_name="multi_para.txt",
        full_text=full_text,
        pages=[
            ExtractedPage(page_number=1, text=full_text, raw_text=full_text)
        ],
    )

    chunks = chunker.chunk_document(
        document=doc,
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )

    assert len(chunks) >= 3
    for chunk in chunks:
        assert chunk.metadata.token_count <= 40
        assert chunk.metadata.page_number == 1

    # Verify sequential indices
    for i, c in enumerate(chunks):
        assert c.metadata.chunk_index == i


def test_chunking_service_page_attribution():
    """Test that chunks correctly preserve their source page numbers across multi-page documents."""
    chunker = ChunkingService(chunk_size_tokens=50, chunk_overlap_tokens=10)
    page_1_text = "Page 1: Overview of system architecture and frontend components."
    page_2_text = "Page 2: PostgreSQL with pgvector integration and HNSW similarity searches."

    doc = ExtractedDocument(
        file_type="PDF",
        file_name="two_page.pdf",
        full_text=f"{page_1_text}\n\n{page_2_text}",
        pages=[
            ExtractedPage(page_number=1, text=page_1_text, raw_text=page_1_text),
            ExtractedPage(page_number=2, text=page_2_text, raw_text=page_2_text),
        ],
    )

    chunks = chunker.chunk_document(
        document=doc,
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )

    p1_chunks = [c for c in chunks if c.metadata.page_number == 1]
    p2_chunks = [c for c in chunks if c.metadata.page_number == 2]

    assert len(p1_chunks) >= 1
    assert len(p2_chunks) >= 1
    assert "Overview of system architecture" in p1_chunks[0].content
    assert "pgvector integration" in p2_chunks[0].content


def test_chunking_service_table_header_repetition():
    """Test that large tables split across chunks repeat the Markdown table headers."""
    chunker = ChunkingService(chunk_size_tokens=35, chunk_overlap_tokens=5)

    headers = "| Metric | Q1 | Q2 |"
    delimiter = "| --- | --- | --- |"
    rows = [f"| Row {i} | Val A{i} | Val B{i} |" for i in range(1, 10)]
    table_md = "\n".join([headers, delimiter] + rows)

    chunks = chunker._chunk_table_respecting_headers(table_md)
    assert len(chunks) >= 2

    # Every continuation chunk MUST contain the table headers
    for c in chunks:
        assert "| Metric | Q1 | Q2 |" in c
        assert "| --- | --- | --- |" in c


def test_chunking_statistics_calculation():
    """Test aggregation of chunking statistics."""
    chunker = ChunkingService(chunk_size_tokens=100, chunk_overlap_tokens=20)
    doc = ExtractedDocument(
        file_type="TXT",
        file_name="stats.txt",
        full_text="Chunk one content.\n\nChunk two content with table:\n| Col 1 | Col 2 |\n| --- | --- |\n| 1 | 2 |",
        pages=[
            ExtractedPage(
                page_number=1,
                text="Chunk one content.\n\nChunk two content with table:\n| Col 1 | Col 2 |\n| --- | --- |\n| 1 | 2 |",
                raw_text="...",
            )
        ],
    )
    chunks = chunker.chunk_document(
        document=doc,
        organization_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
    )
    stats = chunker.calculate_statistics(chunks)

    assert stats.total_chunks == len(chunks)
    assert stats.total_tokens > 0
    assert stats.average_tokens_per_chunk > 0
    assert stats.chunks_with_tables >= 1
