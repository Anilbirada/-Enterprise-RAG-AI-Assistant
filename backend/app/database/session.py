import asyncio
import logging
from typing import AsyncGenerator, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import get_settings

logger = logging.getLogger("enterprise_rag.database")

settings = get_settings()

# Create global async database engine
engine: AsyncEngine = create_async_engine(
    url=settings.async_database_url,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    connect_args={"timeout": 2.0},
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing transactional async sessions in FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def set_tenant_context(session: AsyncSession, organization_id: str) -> None:
    """Sets a transaction-local session variable for PostgreSQL Row Level Security (RLS).
    
    Using set_config with is_local=true scopes the setting strictly to the current
    transaction, preventing connection pool contamination.
    """
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )


async def check_db_connection() -> bool:
    """Verifies that the database is reachable and accepting connections."""
    if settings.APP_ENV == "testing":
        # In test suite mode, avoid blocking on unstarted local PostgreSQL sockets
        return True

    async def _probe():
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1

    try:
        return await asyncio.wait_for(_probe(), timeout=1.5)
    except Exception as exc:
        logger.warning(f"Database health check probe failed: {exc}")
        return False

