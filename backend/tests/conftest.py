import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Enforce testing environment before importing application
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-characters-long"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://test.local"
os.environ["POSTGRES_PORT"] = "5434"
os.environ["POSTGRES_DB"] = "enterprise_rag_test_db"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "postgres"

from app.core.config import Settings, get_settings
from app.main import app
from app.api.deps import get_db

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
test_engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Overrides get_db dependency to point directly to the isolated test database."""
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing isolated test settings."""
    return get_settings()


@pytest.fixture(autouse=True)
def mock_db_connectivity():
    """Autouse fixture to mock database connectivity check in tests where DB is not yet running."""
    with patch("app.main.check_db_connection", new_callable=AsyncMock) as mock_main_check, \
         patch("app.api.v1.endpoints.health.check_db_connection", new_callable=AsyncMock) as mock_endpoint_check, \
         patch("app.database.session.check_db_connection", new_callable=AsyncMock) as mock_session_check:
        mock_main_check.return_value = True
        mock_endpoint_check.return_value = True
        mock_session_check.return_value = True
        yield


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an asynchronous HTTP test client for invoking FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
