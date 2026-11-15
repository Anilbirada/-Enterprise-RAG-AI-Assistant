import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChunkMetadata(BaseModel):
    """Metadata attributes preserved with each individual text chunk."""
    document_id: uuid.UUID
    version_id: uuid.UUID
    organization_id: uuid.UUID
    chunk_index: int
    page_number: Optional[int] = None
    token_count: int
    char_count: int
    has_table: bool = False
    section_title: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class DocumentChunkData(BaseModel):
    """Data transfer object representing a chunk, its metadata, and its embedding vector."""
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None


class ChunkingStatistics(BaseModel):
    """Aggregate statistics summarizing the output of a chunking run."""
    total_chunks: int
    total_tokens: int
    average_tokens_per_chunk: float
    max_tokens: int
    min_tokens: int
    chunks_with_tables: int


class EmbeddingBatchResult(BaseModel):
    """Output envelope returned by the embedding service."""
    embeddings: List[List[float]]
    total_tokens_consumed: int
    model: str
    dimension: int


class ChunkSearchResult(BaseModel):
    """Normalized search result returned by dense vector similarity or sparse keyword search."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    organization_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    score: float
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    has_table: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
