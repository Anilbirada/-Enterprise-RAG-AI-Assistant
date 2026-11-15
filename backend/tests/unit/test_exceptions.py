import pytest
from app.core.exceptions import (
    AppException,
    EntityNotFoundException,
    ForbiddenException,
    TenantIsolationException,
    UnauthorizedException,
)
from app.core.logger import mask_sensitive_data


def test_app_exception_attributes():
    """Verify AppException carries correct HTTP status, error code, and details."""
    exc = AppException(
        message="Custom error",
        status_code=400,
        error_code="BAD_REQUEST",
        details={"field": "query"},
    )
    assert exc.message == "Custom error"
    assert exc.status_code == 400
    assert exc.error_code == "BAD_REQUEST"
    assert exc.details == {"field": "query"}


def test_entity_not_found_exception():
    """Verify EntityNotFoundException format."""
    exc = EntityNotFoundException("Document", "doc-123")
    assert exc.status_code == 404
    assert exc.error_code == "NOT_FOUND"
    assert "Document with identifier 'doc-123' was not found." == exc.message
    assert exc.details == {"entity": "Document", "identifier": "doc-123"}


def test_tenant_isolation_exception():
    """Verify TenantIsolationException is 403 Forbidden with proper error code."""
    exc = TenantIsolationException("Cross-tenant access blocked")
    assert exc.status_code == 403
    assert exc.error_code == "TENANT_ISOLATION_VIOLATION"


def test_mask_sensitive_data_utility():
    """Verify that credentials, tokens, and passwords are never exposed in logs."""
    sample_payload = {
        "username": "alice@company.com",
        "password": "super-secret-password-123",
        "api_key": "sk-1234567890abcdef",
        "nested": {
            "token": "bearer-jwt-token-xyz",
            "safe_field": "public_value",
        },
        "list_data": [
            {"authorization": "Bearer secret"},
            {"item": "book"},
        ],
    }
    masked = mask_sensitive_data(sample_payload)
    assert masked["username"] == "alice@company.com"
    assert masked["password"] == "******"
    assert masked["api_key"] == "******"
    assert masked["nested"]["token"] == "******"
    assert masked["nested"]["safe_field"] == "public_value"
    assert masked["list_data"][0]["authorization"] == "******"
    assert masked["list_data"][1]["item"] == "book"
