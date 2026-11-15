import uuid
from typing import AsyncGenerator, Callable, List, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenException, TenantIsolationException, UnauthorizedException
from app.core.permissions import Permission, Role, has_permission
from app.core.security import decode_access_token
from app.database.session import get_async_session, set_tenant_context
from app.models.organization import Organization
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session per request."""
    async for session in get_async_session():
        yield session


def get_current_settings(settings: Settings = Depends(get_settings)) -> Settings:
    """Dependency returning the application settings instance."""
    return settings


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Extracts, decodes, and validates JWT access token claims, then fetches the authoritative User record.
    
    Crucially, this dependency binds the verified tenant identity transaction-locally
    into PostgreSQL session settings via set_tenant_context(), activating Row Level Security!
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedException("Authentication token is missing. Please provide a Bearer token.")

    token = credentials.credentials
    claims = decode_access_token(token)

    user_id_str = claims.get("sub")
    org_id_str = claims.get("org_id")

    if not user_id_str or not org_id_str:
        raise UnauthorizedException("Invalid token payload: missing required user or tenant subject.")

    try:
        user_uuid = uuid.UUID(user_id_str)
        org_uuid = uuid.UUID(org_id_str)
    except ValueError:
        raise UnauthorizedException("Malformed UUID claims inside token.")

    # 1. Establish transaction-local tenant context for RLS immediately
    await set_tenant_context(session, str(org_uuid))

    # 2. Attach tenant and user identifiers to request.state for middleware/logging
    request.state.tenant_id = str(org_uuid)
    request.state.user_id = str(user_uuid)

    # 3. Query authoritative user record within the verified tenant boundary
    stmt = (
        select(User, Organization)
        .join(Organization, User.organization_id == Organization.id)
        .where(User.id == user_uuid, User.organization_id == org_uuid)
    )
    result = await session.execute(stmt)
    row = result.first()

    if not row:
        raise UnauthorizedException("User not found or does not belong to the claimed organization.")

    user, org = row

    if not org.is_active:
        raise UnauthorizedException("The organization account has been disabled or suspended.")

    if not user.is_active:
        raise UnauthorizedException("User account is inactive. Please contact an administrator.")

    # Attach loaded organization to user instance for downstream access
    user.organization = org
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensures that the authenticated user is currently active."""
    if not current_user.is_active:
        raise UnauthorizedException("User account is inactive.")
    return current_user


async def get_current_organization(
    current_user: User = Depends(get_current_active_user),
) -> Organization:
    """Provides the verified authoritative Organization of the authenticated user."""
    return current_user.organization


def get_current_tenant_id(
    current_user: User = Depends(get_current_active_user),
) -> uuid.UUID:
    """Returns the verified organization ID of the authenticated user."""
    return current_user.organization_id


def require_role(*allowed_roles: str) -> Callable:
    """Factory dependency enforcing that the user possesses one of the allowed roles."""
    async def role_checker(current_user: User = Depends(get_current_active_user)) -> User:
        # SUPER_ADMIN has global privileges
        if current_user.role == Role.SUPER_ADMIN.value or current_user.role in allowed_roles:
            return current_user

        raise ForbiddenException(
            f"Operation requires one of the following roles: {', '.join(allowed_roles)}. "
            f"Your current role is '{current_user.role}'."
        )

    return role_checker


def require_permissions(*required_permissions: Permission) -> Callable:
    """Factory dependency enforcing that the user's role satisfies all required granular permissions."""
    async def permission_checker(current_user: User = Depends(get_current_active_user)) -> User:
        for perm in required_permissions:
            if not has_permission(current_user.role, perm):
                raise ForbiddenException(
                    f"Permission denied: action requires '{perm.value}' permission. "
                    f"Your role '{current_user.role}' does not hold this permission."
                )
        return current_user

    return permission_checker
