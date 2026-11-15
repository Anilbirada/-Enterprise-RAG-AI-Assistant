import uuid
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Initializes tenant context placeholder on request.state for downstream handlers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Default tenant context is None until verified by JWT auth dependency
        request.state.tenant_id = None
        request.state.user_id = None
        
        # Optional header override for internal/testing requests if in dev mode
        dev_tenant_header = request.headers.get("X-Tenant-ID")
        if dev_tenant_header:
            try:
                request.state.tenant_id = str(uuid.UUID(dev_tenant_header))
            except ValueError:
                pass

        return await call_next(request)
