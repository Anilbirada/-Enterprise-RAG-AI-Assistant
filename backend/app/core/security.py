import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException

settings = get_settings()

# Configure Argon2id password hasher
_argon2_hasher = Argon2Hasher(
    time_cost=settings.ARGON2_TIME_COST,
    memory_cost=settings.ARGON2_MEMORY_COST,
    parallelism=settings.ARGON2_PARALLELISM,
)
password_hasher = PasswordHash((_argon2_hasher,))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against an Argon2id hash."""
    return password_hasher.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hashes a password using Argon2id with unique cryptographic salt."""
    return password_hasher.hash(password)


def hash_token(raw_token: str) -> str:
    """Computes a SHA-256 hex digest of a token string for safe database persistence."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: str,
    organization_id: str,
    organization_slug: str,
    role: str,
    department_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a signed, short-lived JWT access token with authoritative security claims."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "org_slug": organization_slug,
        "role": role,
        "dept_id": str(department_id) if department_id else None,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token_string() -> str:
    """Generates a cryptographically secure, high-entropy 256-bit random token string."""
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and rigorously validates an access token's signature, algorithm, and claims."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # Explicit algorithm allowlist
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={
                "require": ["sub", "org_id", "role", "exp", "iat", "jti", "token_type"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException("Access token has expired. Please refresh your session.")
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedException(f"Invalid access token: {str(exc)}")

    if payload.get("token_type") != "access":
        raise UnauthorizedException("Invalid token type. Expected access token.")

    return payload
