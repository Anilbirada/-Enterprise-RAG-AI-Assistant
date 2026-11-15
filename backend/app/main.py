from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app import __version__
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.logger import setup_logging
from app.database.session import check_db_connection, engine
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.middleware.tenant_context_middleware import TenantContextMiddleware

settings = get_settings()
logger = setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager handling startup and shutdown events."""
    logger.info(
        f"Starting {settings.APP_NAME} v{__version__} [Environment: {settings.APP_ENV}]"
    )

    # Startup checks
    db_ok = await check_db_connection()
    if db_ok:
        logger.info("Database connection verified successfully.")
    else:
        logger.warning(
            "Database connection could not be established at startup. "
            "Application will run in degraded mode until PostgreSQL is available."
        )

    yield

    # Graceful shutdown
    logger.info("Shutting down application and releasing database connection pool...")
    await engine.dispose()
    logger.info("Application shutdown complete.")


def create_application() -> FastAPI:
    """Factory creating and configuring the FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description=(
            "Production-grade Enterprise Retrieval-Augmented Generation (RAG) Platform "
            "with multi-tenant isolation, hybrid retrieval, and grounded AI generation."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # 1. Register CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Register Custom HTTP Middlewares (Order: Logging outermost, Context innermost)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(TenantContextMiddleware)

    # 3. Register Global Exception Handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    # 4. Register API Routers
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    # 5. Top-level Root Endpoint
    @app.get("/", tags=["General"])
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": __version__,
            "environment": settings.APP_ENV,
            "status": "online",
            "docs_url": "/docs",
            "api_v1_prefix": settings.API_V1_STR,
        }

    # Top-level /health alias for container health checks
    @app.get("/health", tags=["Health & Monitoring"], include_in_schema=False)
    async def root_health_alias():
        db_healthy = await check_db_connection()
        return JSONResponse(
            status_code=200 if db_healthy else 503,
            content={"status": "healthy" if db_healthy else "degraded"},
        )

    return app


app = create_application()
