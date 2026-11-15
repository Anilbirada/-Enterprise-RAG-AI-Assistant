from datetime import datetime
from typing import Dict, Literal
from pydantic import BaseModel, Field


class ServiceStatus(BaseModel):
    """Status details for an individual subsystem."""
    status: Literal["healthy", "degraded", "unhealthy"]
    details: str | None = None


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    environment: str
    timestamp: datetime
    services: Dict[str, ServiceStatus] = Field(default_factory=dict)
