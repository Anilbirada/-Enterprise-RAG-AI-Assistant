import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token_string,
    hash_token,
    verify_password,
)
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenResponse

logger = logging.getLogger("enterprise_rag.auth_service")
settings = get_settings()

GENERIC_AUTH_ERROR = "Invalid organization, email, or password."


class AuthService:
    """Enterprise authentication lifecycle service."""

    @staticmethod
    async def authenticate_user(
        session: AsyncSession,
        organization_slug: str,
        email: str,
        password: str,
    ) -> tuple[User, Organization]:
        """Authenticates user against a verified organization slug with constant-time password check."""
        # 1. Resolve organization by slug (Tenant lookup)
        stmt_org = select(Organization).where(Organization.slug == organization_slug.strip().lower())
        result_org = await session.execute(stmt_org)
        org = result_org.scalar_one_or_none()

        if not org or not org.is_active:
            logger.warning(f"Failed login attempt: unknown or inactive organization slug '{organization_slug}'")
            raise UnauthorizedException(GENERIC_AUTH_ERROR)

        # 2. Resolve user within that verified organization
        stmt_user = select(User).where(
            User.organization_id == org.id,
            User.email == email.strip().lower(),
        )
        result_user = await session.execute(stmt_user)
        user = result_user.scalar_one_or_none()

        if not user or not user.is_active:
            logger.warning(f"Failed login attempt: unknown or inactive user '{email}' in org '{org.slug}'")
            raise UnauthorizedException(GENERIC_AUTH_ERROR)

        # 3. Verify Argon2id password hash
        if not verify_password(password, user.hashed_password):
            logger.warning(f"Failed login attempt: invalid password for user '{email}' in org '{org.slug}'")
            raise UnauthorizedException(GENERIC_AUTH_ERROR)

        # 4. Update last login timestamp
        user.last_login_at = datetime.now(timezone.utc)
        await session.flush()

        logger.info(f"User '{user.email}' authenticated successfully for tenant '{org.slug}'")
        return user, org

    @staticmethod
    async def create_session(
        session: AsyncSession,
        user: User,
        org: Organization,
    ) -> TokenResponse:
        """Issues short-lived JWT access token and persists a new rotating refresh token."""
        # Issue short-lived access token
        access_token = create_access_token(
            user_id=str(user.id),
            organization_id=str(org.id),
            organization_slug=org.slug,
            role=user.role,
            department_id=str(user.department_id) if user.department_id else None,
        )

        # Issue rotating refresh token
        raw_refresh_token = create_refresh_token_string()
        token_digest = hash_token(raw_refresh_token)
        family_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        refresh_record = RefreshToken(
            organization_id=org.id,
            user_id=user.id,
            token_hash=token_digest,
            family_id=family_id,
            is_revoked=False,
            expires_at=expires_at,
            created_at=now,
        )
        session.add(refresh_record)
        await session.flush()

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def rotate_refresh_token(
        session: AsyncSession,
        raw_refresh_token: str,
    ) -> TokenResponse:
        """Rotates a refresh token with strict token family tracking and reuse detection."""
        token_digest = hash_token(raw_refresh_token.strip())

        # Lookup token by cryptographic hash
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_digest)
        result = await session.execute(stmt)
        token_record = result.scalar_one_or_none()

        if not token_record:
            logger.warning("Token refresh failed: token digest not recognized")
            raise UnauthorizedException("Invalid or unrecognized refresh token.")

        # REUSE DETECTION: If a previously revoked token is presented, compromise is assumed!
        if token_record.is_revoked:
            logger.critical(
                f"SECURITY ALERT: Refresh token reuse detected for family {token_record.family_id}! "
                f"Revoking all active tokens in this family immediately."
            )
            # Revoke entire token family and commit immediately so it persists despite the exception rollback
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token_record.family_id)
                .values(is_revoked=True, revoked_at=datetime.now(timezone.utc))
            )
            await session.commit()
            raise UnauthorizedException("Refresh token reuse detected. All active sessions have been revoked.")

        now = datetime.now(timezone.utc)
        # Check token expiration
        if token_record.expires_at < now:
            token_record.is_revoked = True
            token_record.revoked_at = now
            await session.commit()
            logger.info(f"Token refresh rejected: token expired on {token_record.expires_at}")
            raise UnauthorizedException("Refresh token has expired. Please log in again.")

        # Authoritative User & Organization check
        stmt_user = (
            select(User, Organization)
            .join(Organization, User.organization_id == Organization.id)
            .where(User.id == token_record.user_id)
        )
        res_user = await session.execute(stmt_user)
        user_org = res_user.first()

        if not user_org:
            raise UnauthorizedException("Associated user or organization not found.")
        user, org = user_org

        if not user.is_active or not org.is_active:
            raise UnauthorizedException("User account or organization is currently disabled.")

        # Invalidate old token (One-time use)
        token_record.is_revoked = True
        token_record.revoked_at = now

        # Generate successor token in the same family
        new_raw_refresh = create_refresh_token_string()
        new_digest = hash_token(new_raw_refresh)
        token_record.replaced_by_hash = new_digest

        new_token_record = RefreshToken(
            organization_id=org.id,
            user_id=user.id,
            token_hash=new_digest,
            family_id=token_record.family_id,
            is_revoked=False,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=now,
        )
        session.add(new_token_record)

        # Issue fresh short-lived access token
        access_token = create_access_token(
            user_id=str(user.id),
            organization_id=str(org.id),
            organization_slug=org.slug,
            role=user.role,
            department_id=str(user.department_id) if user.department_id else None,
        )
        await session.flush()

        logger.info(f"Successfully rotated refresh token for user '{user.email}' (family: {token_record.family_id})")
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @staticmethod
    async def revoke_refresh_token(
        session: AsyncSession,
        raw_refresh_token: str,
    ) -> bool:
        """Revokes a refresh token session during logout."""
        token_digest = hash_token(raw_refresh_token.strip())
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_digest,
            RefreshToken.is_revoked.is_(False),
        )
        result = await session.execute(stmt)
        token_record = result.scalar_one_or_none()

        if token_record:
            token_record.is_revoked = True
            token_record.revoked_at = datetime.now(timezone.utc)
            await session.flush()
            logger.info(f"Revoked refresh token for user {token_record.user_id}")
            return True
        return False
