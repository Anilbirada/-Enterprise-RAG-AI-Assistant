from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """Payload to create a new chat conversation session."""
    title: Optional[str] = Field(default=None, max_length=255, description="Optional title for the conversation")


class CitationResponse(BaseModel):
    """Source citation connecting an assistant claim to a specific document chunk."""
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    rank_position: int
    relevance_score: float
    snippet: str
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    citation_number: Optional[int] = None
    document_title: Optional[str] = None


class MessageResponse(BaseModel):
    """Message record representation."""
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    citations: List[CitationResponse] = Field(default_factory=list)


class ConversationResponse(BaseModel):
    """Conversation summary."""
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetailResponse(BaseModel):
    """Conversation detail including ordered message history."""
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]


class ChatCompletionRequest(BaseModel):
    """Request payload for RAG chat completion."""
    conversation_id: Optional[uuid.UUID] = Field(
        default=None, description="Existing conversation ID. If None, a new conversation is created."
    )
    message: str = Field(..., min_length=1, max_length=4000, description="User prompt or question")
    stream: bool = Field(default=True, description="Whether to stream response via Server-Sent Events (SSE)")
    retrieval_method: Literal["HYBRID", "DENSE"] = Field(
        default="HYBRID", description="Retrieval strategy: HYBRID (dense+sparse RRF) or DENSE"
    )
    retrieval_limit: int = Field(default=5, ge=1, le=20, description="Number of context chunks to retrieve")
    similarity_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity cutoff")
    document_ids: Optional[List[uuid.UUID]] = Field(default=None, description="Optional document filter list")
    department_id: Optional[uuid.UUID] = Field(default=None, description="Optional department filter")


class ChatCompletionResponse(BaseModel):
    """Non-streaming response envelope for RAG chat completion."""
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    role: str = "ASSISTANT"
    content: str
    citations: List[CitationResponse]
    tokens_used: int
    latency_ms: float
