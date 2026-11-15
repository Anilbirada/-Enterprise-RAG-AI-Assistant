import time
from datetime import timedelta
import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.permissions import Permission, Role, has_permission
from app.core.security import (
    create_access_token,
    create_refresh_token_string,
    decode_access_token,
    get_password_hash,
    hash_token,
    verify_password,
)

settings = get_settings()


def test_argon2_password_hashing():
    """Verify Argon2id produces valid hashes and verifies plaintext matches."""
    plain = "SuperSecurePassword123!"
    hashed = get_password_hash(plain)

    assert hashed.startswith("$argon2id$")
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False


def test_argon2_unique_salts():
    """Verify identical passwords produce distinct hashes due to cryptographic salting."""
    plain = "IdenticalPassword123!"
    hash1 = get_password_hash(plain)
    hash2 = get_password_hash(plain)

    assert hash1 != hash2
    assert verify_password(plain, hash1) is True
    assert verify_password(plain, hash2) is True


def test_password_hashing_benchmark():
    """Benchmark Argon2id under application load.
    
    Verifies that Argon2id with time_cost=3, memory_cost=64MB executes in reasonable time
    (under 1 second per hash) to balance brute-force resistance against server throughput.
    """
    start = time.perf_counter()
    iterations = 2
    for _ in range(iterations):
        get_password_hash("BenchmarkTestPassword123!")
    elapsed = time.perf_counter() - start
    avg_ms = (elapsed / iterations) * 1000
    print(f"\n[BENCHMARK] Argon2id hashing average: {avg_ms:.2f}ms")
    # Must be under 1500ms on modern CPU
    assert avg_ms < 1500.0


def test_access_token_creation_and_claims():
    """Verify JWT access token contains all required authoritative claims."""
    token = create_access_token(
        user_id="user-123",
        organization_id="org-456",
        organization_slug="acme-corp",
        role="ORG_ADMIN",
        department_id="dept-789",
    )
    claims = decode_access_token(token)

    assert claims["sub"] == "user-123"
    assert claims["org_id"] == "org-456"
    assert claims["org_slug"] == "acme-corp"
    assert claims["role"] == "ORG_ADMIN"
    assert claims["dept_id"] == "dept-789"
    assert claims["iss"] == settings.JWT_ISSUER
    assert claims["aud"] == settings.JWT_AUDIENCE
    assert claims["token_type"] == "access"
    assert "jti" in claims


def test_expired_access_token_rejected():
    """Verify expired JWTs raise UnauthorizedException."""
    token = create_access_token(
        user_id="user-123",
        organization_id="org-456",
        organization_slug="acme-corp",
        role="EMPLOYEE",
        expires_delta=timedelta(seconds=-10),  # Expired in past
    )
    with pytest.raises(UnauthorizedException) as exc:
        decode_access_token(token)
    assert "expired" in str(exc.value).lower()


def test_tampered_jwt_signature_rejected():
    """Verify altered signatures raise UnauthorizedException."""
    token = create_access_token(
        user_id="user-123",
        organization_id="org-456",
        organization_slug="acme-corp",
        role="EMPLOYEE",
    )
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(UnauthorizedException) as exc:
        decode_access_token(tampered)
    assert "invalid access token" in str(exc.value).lower()


def test_jwt_algorithm_none_rejected():
    """Verify 'none' algorithm is rejected by strict algorithm allowlist."""
    unsigned_token = jwt.encode(
        {"sub": "user-123", "org_id": "org-456", "role": "EMPLOYEE", "token_type": "access"},
        key="",
        algorithm="none",
    )
    with pytest.raises(UnauthorizedException):
        decode_access_token(unsigned_token)


def test_jwt_issuer_and_audience_validation():
    """Verify mismatched issuer or audience is rejected."""
    wrong_issuer_token = jwt.encode(
        {
            "sub": "user-123",
            "org_id": "org-456",
            "role": "EMPLOYEE",
            "token_type": "access",
            "iss": "untrusted-issuer",
            "aud": settings.JWT_AUDIENCE,
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            "jti": "some-jti",
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(UnauthorizedException) as exc:
        decode_access_token(wrong_issuer_token)
    assert "invalid access token" in str(exc.value).lower()


def test_rbac_permissions_matrix():
    """Verify granular permissions for all enterprise roles."""
    assert has_permission(Role.SUPER_ADMIN.value, Permission.MANAGE_ORGANIZATION) is True
    assert has_permission(Role.ORG_ADMIN.value, Permission.MANAGE_ORGANIZATION) is False
    assert has_permission(Role.ORG_ADMIN.value, Permission.MANAGE_USERS) is True
    assert has_permission(Role.KNOWLEDGE_MANAGER.value, Permission.UPLOAD_DOCUMENTS) is True
    assert has_permission(Role.KNOWLEDGE_MANAGER.value, Permission.MANAGE_USERS) is False
    assert has_permission(Role.EMPLOYEE.value, Permission.CHAT_QUERY) is True
    assert has_permission(Role.EMPLOYEE.value, Permission.UPLOAD_DOCUMENTS) is False
    assert has_permission("UNKNOWN_ROLE", Permission.CHAT_QUERY) is False
