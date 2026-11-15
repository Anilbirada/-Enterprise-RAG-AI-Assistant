import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """User authentication payload requiring explicit tenant slug identification."""

    organization_slug: str = Field(
        ...,
        min_length=2,
        max_length=60,
        description="The unique slug of the organization (e.g. 'acme-corp')",
        examples=["acme-corp"],
    )
    email: EmailStr = Field(
        ...,
        description="Registered user email address",
        examples=["alice@acme.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        description="User plaintext password",
    )


class TokenResponse(BaseModel):
    """OAuth2 / JWT token response envelope."""

    access_token: str = Field(..., description="Short-lived signed JWT access token")
    refresh_token: str = Field(..., description="High-entropy opaque refresh token string")
    token_type: str = Field(default="bearer", description="Token scheme")
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class RefreshTokenRequest(BaseModel):
    """Payload to rotate and refresh an access token."""

    refresh_token: str = Field(..., description="Valid rotating refresh token")


class LogoutRequest(BaseModel):
    """Payload to revoke active session refresh token."""

    refresh_token: str = Field(..., description="Refresh token to revoke")


class UserResponse(BaseModel):
    """Authoritative user profile representation."""

    id: uuid.UUID
    organization_id: uuid.UUID
    department_id: Optional[uuid.UUID] = None
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
