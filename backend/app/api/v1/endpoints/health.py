from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from app import __version__
from app.core.config import Settings, get_settings
from app.database.session import check_db_connection
from app.schemas.health import HealthResponse, ServiceStatus

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Comprehensive System Health Check",
    description="Inspects the operational status of the API server and its database connectivity.",
)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    db_healthy = await check_db_connection()
    overall_status = "healthy" if db_healthy else "degraded"

    services = {
        "database": ServiceStatus(
            status="healthy" if db_healthy else "unhealthy",
            details="Connected to PostgreSQL" if db_healthy else "Database connection failed",
        ),
        "api": ServiceStatus(
            status="healthy",
            details="FastAPI application runtime operational",
        ),
    }

    return HealthResponse(
        status=overall_status,
        version=__version__,
        environment=settings.APP_ENV,
        timestamp=datetime.now(timezone.utc),
        services=services,
    )


@router.get(
    "/ready",
    summary="Container Readiness Probe",
    description="Returns 200 OK only when the service is fully prepared to receive network traffic.",
)
async def readiness_probe() -> JSONResponse:
    db_ready = await check_db_connection()
    if not db_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ready": False, "reason": "Database connection unavailable"},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"ready": True},
    )


@router.get(
    "/live",
    summary="Container Liveness Probe",
    description="Returns 200 OK as long as the application process is running.",
)
async def liveness_probe() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"alive": True},
    )
