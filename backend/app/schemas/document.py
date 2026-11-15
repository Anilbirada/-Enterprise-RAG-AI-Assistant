import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentVersionResponse(BaseModel):
    """Schema for individual document version entries."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    file_hash: str
    file_size_bytes: int
    is_active: bool
    created_at: datetime


class IngestionJobSummaryResponse(BaseModel):
    """Summary schema for background ingestion job status."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class DocumentResponse(BaseModel):
    """Core response schema for Document entities."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: Optional[uuid.UUID] = None
    uploaded_by_id: uuid.UUID
    title: str
    file_name: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    status: str
    error_message: Optional[str] = None
    current_version_id: Optional[uuid.UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class DocumentDetailResponse(DocumentResponse):
    """Detailed response schema including historical versions and latest processing job."""
    versions: List[DocumentVersionResponse] = Field(default_factory=list)
    latest_job: Optional[IngestionJobSummaryResponse] = None


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload and staging."""
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    version_id: uuid.UUID
    job_id: uuid.UUID
    organization_id: uuid.UUID
    department_id: Optional[uuid.UUID] = None
    title: str
    file_name: str
    file_type: str
    file_size_bytes: int
    file_hash: str
    status: str
    created_at: datetime


class DocumentStatusResponse(BaseModel):
    """Lightweight polling response for document processing status."""
    document_id: uuid.UUID
    title: str
    document_status: str
    current_version_id: Optional[uuid.UUID] = None
    job_id: Optional[uuid.UUID] = None
    job_status: Optional[str] = None
    error_message: Optional[str] = None
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated list envelope for document collections."""
    items: List[DocumentResponse]
    total: int
    skip: int
    limit: int


class DocumentDeleteResponse(BaseModel):
    """Response schema following document deletion."""
    success: bool = True
    message: str
    document_id: uuid.UUID
