from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login with Tenant Disambiguation",
    description=(
        "Authenticates a user using their registered organization slug, email, and password. "
        "Returns a short-lived JWT access token and a rotating refresh token."
    ),
)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user, org = await AuthService.authenticate_user(
        session=session,
        organization_slug=payload.organization_slug,
        email=payload.email,
        password=payload.password,
    )
    return await AuthService.create_session(session=session, user=user, org=org)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate and Refresh Access Token",
    description=(
        "Exchanges an active refresh token for a fresh access token and a new rotating refresh token. "
        "Implements strict token family tracking and automatic reuse breach revocation."
    ),
)
async def refresh_token(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await AuthService.rotate_refresh_token(
        session=session,
        raw_refresh_token=payload.refresh_token,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="User Logout & Token Revocation",
    description="Revokes the presented refresh token session.",
)
async def logout(
    payload: LogoutRequest,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await AuthService.revoke_refresh_token(
        session=session,
        raw_refresh_token=payload.refresh_token,
    )
    return {"success": True, "message": "Session successfully terminated."}


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Authenticated User Profile",
    description="Returns the authoritative profile of the currently authenticated user.",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user
