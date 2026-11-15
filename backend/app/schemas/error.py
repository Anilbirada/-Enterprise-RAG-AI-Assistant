from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Structured error payload definition."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable description of the error")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Supplementary error contextual details")


class ErrorResponse(BaseModel):
    """Standardized API error response envelope."""
    success: bool = Field(default=False, description="Always false for error responses")
    error: ErrorDetail
    request_id: Optional[str] = Field(default=None, description="Unique correlation ID for tracing")
