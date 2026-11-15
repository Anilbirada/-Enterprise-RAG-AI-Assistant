import uuid
import pytest

from app.schemas.chunk import ChunkSearchResult
from app.services.rag.citation_service import CitationService
from app.services.rag.prompt_templates import (
    SYSTEM_PROMPT,
    build_rag_messages,
    format_rag_context,
)


def make_dummy_chunk(
    doc_id: uuid.UUID,
    chunk_index: int,
    content: str,
    page_number: int = 1,
    score: float = 0.9,
) -> ChunkSearchResult:
    return ChunkSearchResult(
        chunk_id=uuid.uuid4(),
        document_id=doc_id,
        version_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        chunk_index=chunk_index,
        content=content,
        token_count=10,
        score=score,
        page_number=page_number,
        section_title=f"Section {chunk_index}",
    )


def test_format_rag_context_empty():
    """Test format_rag_context handles empty candidate lists."""
    assert format_rag_context([]) == "No relevant corporate documents found."


def test_format_rag_context_populated():
    """Test format_rag_context numbers and structures sources with metadata."""
    doc_id = uuid.uuid4()
    chunks = [
        make_dummy_chunk(doc_id, 0, "First chunk text.", page_number=2),
        make_dummy_chunk(doc_id, 1, "Second chunk text.", page_number=3),
    ]

    formatted = format_rag_context(chunks)
    assert "[Context Source 1]" in formatted
    assert "[Context Source 2]" in formatted
    assert "First chunk text." in formatted
    assert "Second chunk text." in formatted
    assert "Page: 2" in formatted
    assert "Page: 3" in formatted


def test_build_rag_messages():
    """Test prompt building includes system instructions, context, and conversation history."""
    chunks = [make_dummy_chunk(uuid.uuid4(), 0, "Corporate holiday policy is 12 days.")]
    history = [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "How can I help you today?"},
    ]

    messages = build_rag_messages(
        query="How many holidays do we get?",
        context_chunks=chunks,
        conversation_history=history,
    )

    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert "ZERO HALLUCINATION" in messages[0]["content"]

    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hello!"

    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "How can I help you today?"

    assert messages[3]["role"] == "user"
    assert "Corporate holiday policy is 12 days." in messages[3]["content"]
    assert "USER QUESTION: How many holidays do we get?" in messages[3]["content"]


def test_citation_extraction_exact_match():
    """Test CitationService parses [1] and [2] citations from response text."""
    doc_1 = uuid.uuid4()
    doc_2 = uuid.uuid4()
    chunks = [
        make_dummy_chunk(doc_1, 0, "PostgreSQL 16 handles vector queries."),
        make_dummy_chunk(doc_2, 1, "FastAPI routes HTTP requests asynchronously."),
    ]

    response_text = (
        "We use PostgreSQL for vector search [1]. "
        "Additionally, FastAPI handles the REST API routes [2]."
    )

    citations = CitationService.extract_citations(response_text, chunks)

    assert len(citations) == 2
    assert citations[0].rank_position == 1
    assert citations[0].document_id == doc_1
    assert "PostgreSQL 16" in citations[0].snippet

    assert citations[1].rank_position == 2
    assert citations[1].document_id == doc_2
    assert "FastAPI" in citations[1].snippet


def test_citation_extraction_ignores_out_of_bounds():
    """Test CitationService ignores citation numbers that exceed candidate length."""
    chunks = [make_dummy_chunk(uuid.uuid4(), 0, "Only one chunk available.")]
    response_text = "Here is a statement [1] and an invalid reference [99]."

    citations = CitationService.extract_citations(response_text, chunks)

    assert len(citations) == 1
    assert citations[0].rank_position == 1


def test_citation_fallback_when_no_brackets():
    """Test CitationService attributes top chunk if model produced no brackets but retrieved high-scoring chunk."""
    chunks = [make_dummy_chunk(uuid.uuid4(), 0, "Crucial architecture standard.", score=0.92)]
    response_text = "The system follows corporate architecture guidelines."

    citations = CitationService.extract_citations(response_text, chunks)

    assert len(citations) == 1
    assert citations[0].rank_position == 1
    assert "Crucial architecture standard." in citations[0].snippet
