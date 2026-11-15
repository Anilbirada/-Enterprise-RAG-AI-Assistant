import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("enterprise_rag.exceptions")


class AppException(Exception):
    """Base exception class for domain and application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class EntityNotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, entity_name: str, identifier: Any):
        super().__init__(
            message=f"{entity_name} with identifier '{identifier}' was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
            details={"entity": entity_name, "identifier": str(identifier)},
        )


class UnauthorizedException(AppException):
    """Raised when authentication credentials are missing or invalid."""

    def __init__(self, message: str = "Authentication credentials are invalid or missing."):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )


class ForbiddenException(AppException):
    """Raised when an authenticated user lacks required permissions."""

    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )


class TenantIsolationException(AppException):
    """Raised when cross-tenant access is attempted or tenant context is missing."""

    def __init__(self, message: str = "Access denied due to tenant isolation boundary."):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="TENANT_ISOLATION_VIOLATION",
        )


class ConflictException(AppException):
    """Raised when a resource state conflict occurs (e.g. duplicate key or file hash)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
            details=details,
        )


class ValidationException(AppException):
    """Raised when domain or file validation fails (e.g. invalid file extension, signature, size limit)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class ExternalServiceException(AppException):
    """Raised when an external dependency (LLM API, vector store) fails."""

    def __init__(self, service_name: str, message: str):
        super().__init__(
            message=f"External dependency '{service_name}' failed: {message}",
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="EXTERNAL_SERVICE_ERROR",
            details={"service": service_name},
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """FastAPI handler for custom domain AppException instances."""
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        f"Domain exception: [{exc.error_code}] {exc.message}",
        extra={"request_id": request_id, "error_code": exc.error_code, "details": exc.details},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            },
            "request_id": request_id,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI handler for Pydantic schema validation errors."""
    request_id = getattr(request.state, "request_id", None)
    errors = [
        {
            "field": ".".join(str(loc) for loc in err["loc"]),
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    logger.info(
        "Request validation failed",
        extra={"request_id": request_id, "validation_errors": errors},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Input validation failed for the request payload.",
                "details": {"validation_errors": errors},
            },
            "request_id": request_id,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled server exceptions (500). Prevents leaking internal traces."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        f"Unhandled server error occurred: {str(exc)}",
        exc_info=True,
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please contact system support.",
                "details": {},
            },
            "request_id": request_id,
        },
    )
