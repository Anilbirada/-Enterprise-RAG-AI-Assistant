import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("enterprise_rag.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that injects a correlation ID and logs execution latency."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Extract or generate correlation ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id

        start_time = time.perf_counter()

        logger.info(
            f"--> {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"<-- {request.method} {request.url.path} FAILED after {duration_ms:.2f}ms: {exc}",
                exc_info=True,
                extra={"request_id": request_id, "duration_ms": duration_ms},
            )
            from app.core.exceptions import generic_exception_handler
            return await generic_exception_handler(request, exc)

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

        logger.info(
            f"<-- {request.method} {request.url.path} {response.status_code} ({duration_ms:.2f}ms)",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
