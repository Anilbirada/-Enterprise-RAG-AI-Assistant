import uuid
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.chunk import ChunkSearchResult


class SemanticSearchRequest(BaseModel):
    """Payload for dense vector similarity search."""
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language search query")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of chunks to return")
    similarity_threshold: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum cosine similarity cutoff [0.0 - 1.0]"
    )
    document_ids: Optional[List[uuid.UUID]] = Field(
        default=None, description="Optional document ID filter list"
    )
    department_id: Optional[uuid.UUID] = Field(
        default=None, description="Optional department filter"
    )


class HybridSearchRequest(BaseModel):
    """Payload for hybrid search combining dense vector retrieval and sparse full-text search with RRF."""
    query: str = Field(..., min_length=1, max_length=1000, description="Natural language or keyword query")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of merged results to return")
    dense_weight: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Weight multiplier for dense vector rank [0.0 - 1.0]"
    )
    sparse_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Weight multiplier for sparse keyword rank [0.0 - 1.0]"
    )
    rrf_k: int = Field(
        default=60, ge=1, le=200, description="Reciprocal Rank Fusion smoothing constant k (standard: 60)"
    )
    similarity_threshold: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum similarity cutoff for dense candidates"
    )
    document_ids: Optional[List[uuid.UUID]] = Field(
        default=None, description="Optional document ID filter list"
    )
    department_id: Optional[uuid.UUID] = Field(
        default=None, description="Optional department filter"
    )


class SearchResponse(BaseModel):
    """Unified response envelope for semantic and hybrid search queries."""
    query: str
    retrieval_method: str
    total_candidates: int
    execution_time_ms: float
    results: List[ChunkSearchResult]
