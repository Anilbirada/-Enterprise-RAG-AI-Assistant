import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Verify root endpoint returns service metadata and links."""
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Enterprise RAG AI Assistant"
    assert data["status"] == "online"
    assert "version" in data
    assert "docs_url" in data
    assert "X-Request-ID" in response.headers
    assert "X-Response-Time" in response.headers


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    """Verify comprehensive health check endpoint."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "services" in data
    assert "api" in data["services"]
    assert "database" in data["services"]


@pytest.mark.asyncio
async def test_liveness_probe(async_client: AsyncClient):
    """Verify container liveness endpoint."""
    response = await async_client.get("/api/v1/live")
    assert response.status_code == 200
    assert response.json() == {"alive": True}


@pytest.mark.asyncio
async def test_correlation_id_propagation(async_client: AsyncClient):
    """Verify custom X-Request-ID header is preserved and echoed back."""
    custom_request_id = "test-req-id-12345"
    response = await async_client.get(
        "/",
        headers={"X-Request-ID": custom_request_id},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_request_id
