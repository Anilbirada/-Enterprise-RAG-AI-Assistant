import pytest
from httpx import AsyncClient
from fastapi import APIRouter
from app.core.exceptions import AppException, EntityNotFoundException, TenantIsolationException
from app.main import app

test_router = APIRouter(prefix="/test-errors")


@test_router.get("/app-error")
async def trigger_app_error():
    raise AppException(
        message="Simulated application failure",
        status_code=400,
        error_code="SIMULATED_FAILURE",
        details={"reason": "test"},
    )


@test_router.get("/not-found")
async def trigger_not_found():
    raise EntityNotFoundException(entity_name="Workspace", identifier="ws-999")


@test_router.get("/tenant-violation")
async def trigger_tenant_violation():
    raise TenantIsolationException()


@test_router.get("/unexpected-error")
async def trigger_unexpected():
    raise RuntimeError("Unexpected internal crash")


app.include_router(test_router)


@pytest.mark.asyncio
async def test_app_exception_envelope(async_client: AsyncClient):
    """Verify custom AppException formats into standard envelope."""
    response = await async_client.get("/test-errors/app-error")
    assert response.status_code == 400
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "SIMULATED_FAILURE"
    assert data["error"]["message"] == "Simulated application failure"
    assert data["error"]["details"] == {"reason": "test"}
    assert "request_id" in data


@pytest.mark.asyncio
async def test_entity_not_found_handling(async_client: AsyncClient):
    """Verify EntityNotFoundException formats into 404 envelope."""
    response = await async_client.get("/test-errors/not-found")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_generic_exception_masking(async_client: AsyncClient):
    """Verify unhandled 500 exceptions do not leak stack traces."""
    response = await async_client.get("/test-errors/unexpected-error")
    assert response.status_code == 500
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert "Unexpected internal crash" not in data["error"]["message"]
