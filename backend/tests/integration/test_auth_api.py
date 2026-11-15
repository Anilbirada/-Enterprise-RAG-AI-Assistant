import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token, get_password_hash
from app.models.organization import Organization
from app.models.user import User
from app.models.document import Document
from app.main import app
from fastapi import APIRouter, Depends
from app.api.deps import require_role, get_current_user

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
APP_USER_TEST_DB_URL = "postgresql+asyncpg://rag_app_user:rag_app_password@127.0.0.1:5434/enterprise_rag_test_db"

engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

# Add a test admin-only route to test RBAC enforcement
admin_test_router = APIRouter(prefix="/test-admin")


@admin_test_router.get("/users", dependencies=[Depends(require_role("ORG_ADMIN", "SUPER_ADMIN"))])
async def list_admin_users(current_user: User = Depends(get_current_user)):
    return {"status": "authorized", "admin": current_user.email}


app.include_router(admin_test_router)


@pytest.fixture
async def setup_test_orgs_and_users():
    """Seeds test organizations and users in real PostgreSQL database."""
    async with SessionLocal() as session:
        # Organization 1: Alpha
        org_a = Organization(
            id=uuid.uuid4(),
            name="Alpha Corp",
            slug=f"alpha-{uuid.uuid4().hex[:6]}",
            settings={"plan": "enterprise"},
            is_active=True,
        )
        # Organization 2: Beta
        org_b = Organization(
            id=uuid.uuid4(),
            name="Beta LLC",
            slug=f"beta-{uuid.uuid4().hex[:6]}",
            settings={"plan": "standard"},
            is_active=True,
        )
        # Organization 3: Disabled Org
        org_disabled = Organization(
            id=uuid.uuid4(),
            name="Disabled Corp",
            slug=f"disabled-{uuid.uuid4().hex[:6]}",
            is_active=False,
        )
        session.add_all([org_a, org_b, org_disabled])
        await session.flush()

        pw_hash = get_password_hash("Password123!")

        # User in Org A (Admin)
        user_a_admin = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email="admin@shared.com",
            hashed_password=pw_hash,
            full_name="Alice Admin",
            role="ORG_ADMIN",
            is_active=True,
        )
        # User in Org A (Employee)
        user_a_emp = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email="employee@shared.com",
            hashed_password=pw_hash,
            full_name="Bob Employee",
            role="EMPLOYEE",
            is_active=True,
        )
        # User in Org A (Disabled)
        user_a_disabled = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email="disabled@shared.com",
            hashed_password=pw_hash,
            full_name="Charlie Disabled",
            role="EMPLOYEE",
            is_active=False,
        )
        # DUPLICATE EMAIL in Org B with DIFFERENT password
        pw_hash_b = get_password_hash("BetaPassword123!")
        user_b = User(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            email="admin@shared.com",  # Same email, different tenant!
            hashed_password=pw_hash_b,
            full_name="Alice Beta",
            role="ORG_ADMIN",
            is_active=True,
        )
        # User in Disabled Org
        user_in_disabled_org = User(
            id=uuid.uuid4(),
            organization_id=org_disabled.id,
            email="victim@disabled.com",
            hashed_password=pw_hash,
            full_name="Victim User",
            role="EMPLOYEE",
            is_active=True,
        )

        session.add_all([user_a_admin, user_a_emp, user_a_disabled, user_b, user_in_disabled_org])
        await session.commit()

        yield {
            "org_a": org_a,
            "org_b": org_b,
            "org_disabled": org_disabled,
            "user_a_admin": user_a_admin,
            "user_a_emp": user_a_emp,
            "user_a_disabled": user_a_disabled,
            "user_b": user_b,
            "user_in_disabled_org": user_in_disabled_org,
        }


@pytest.mark.asyncio
async def test_successful_login(async_client: AsyncClient, setup_test_orgs_and_users):
    """1. Test successful user login returns valid access and refresh tokens."""
    data = setup_test_orgs_and_users
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "admin@shared.com",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900


@pytest.mark.asyncio
async def test_invalid_password(async_client: AsyncClient, setup_test_orgs_and_users):
    """2. Test login with wrong password returns 401 generic error."""
    data = setup_test_orgs_and_users
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "admin@shared.com",
            "password": "WrongPassword123!",
        },
    )
    assert resp.status_code == 401
    assert "Invalid organization, email, or password" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_invalid_organization_slug(async_client: AsyncClient, setup_test_orgs_and_users):
    """3. Test login with unknown organization slug returns generic 401 error."""
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "non-existent-org-slug",
            "email": "admin@shared.com",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 401
    assert "Invalid organization, email, or password" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_duplicate_emails_across_different_organizations(async_client: AsyncClient, setup_test_orgs_and_users):
    """4. Test same email in Org A and Org B logs into their respective tenants."""
    data = setup_test_orgs_and_users

    # Login to Org A
    resp_a = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "admin@shared.com",
            "password": "Password123!",
        },
    )
    assert resp_a.status_code == 200
    token_a = resp_a.json()["access_token"]

    # Check /me for Org A
    me_a = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_a.status_code == 200
    assert me_a.json()["organization_id"] == str(data["org_a"].id)

    # Login to Org B using Org B's password
    resp_b = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_b"].slug,
            "email": "admin@shared.com",
            "password": "BetaPassword123!",
        },
    )
    assert resp_b.status_code == 200
    token_b = resp_b.json()["access_token"]

    # Check /me for Org B
    me_b = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_b.status_code == 200
    assert me_b.json()["organization_id"] == str(data["org_b"].id)


@pytest.mark.asyncio
async def test_token_refresh_and_rotation(async_client: AsyncClient, setup_test_orgs_and_users):
    """8. Test successful refresh token rotation issues new access and refresh tokens."""
    data = setup_test_orgs_and_users

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "admin@shared.com",
            "password": "Password123!",
        },
    )
    first_refresh = login_res.json()["refresh_token"]

    # Rotate token
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["refresh_token"] != first_refresh


@pytest.mark.asyncio
async def test_refresh_token_reuse_detection(async_client: AsyncClient, setup_test_orgs_and_users):
    """9 & 10: Test reuse of a previously rotated refresh token revokes the entire token family."""
    data = setup_test_orgs_and_users

    # Login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "admin@shared.com",
            "password": "Password123!",
        },
    )
    first_refresh = login_res.json()["refresh_token"]

    # Legitimate client rotates token
    legit_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    assert legit_res.status_code == 200
    second_refresh = legit_res.json()["refresh_token"]

    # Attacker reuses the first (now revoked) refresh token!
    attacker_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first_refresh},
    )
    # Must fail with 401 reuse detection!
    assert attacker_res.status_code == 401
    assert "reuse detected" in attacker_res.json()["error"]["message"].lower()

    # Legitimate client's second token must NOW also be revoked because the entire family was nuked!
    subsequent_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second_refresh},
    )
    assert subsequent_res.status_code == 401


@pytest.mark.asyncio
async def test_logout_revocation(async_client: AsyncClient, setup_test_orgs_and_users):
    """11. Test logout explicitly revokes refresh token session."""
    data = setup_test_orgs_and_users

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "admin@shared.com",
            "password": "Password123!",
        },
    )
    refresh_token = login_res.json()["refresh_token"]

    # Logout
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["success"] is True

    # Attempting to refresh with the revoked token must fail
    fail_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert fail_res.status_code == 401


@pytest.mark.asyncio
async def test_disabled_user_login(async_client: AsyncClient, setup_test_orgs_and_users):
    """12. Test disabled user cannot log in."""
    data = setup_test_orgs_and_users
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_a"].slug,
            "email": "disabled@shared.com",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_disabled_organization_login(async_client: AsyncClient, setup_test_orgs_and_users):
    """13. Test user in disabled organization cannot log in."""
    data = setup_test_orgs_and_users
    resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": data["org_disabled"].slug,
            "email": "victim@disabled.com",
            "password": "Password123!",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rbac_employee_denied_admin_endpoint(async_client: AsyncClient, setup_test_orgs_and_users):
    """14. Test EMPLOYEE role cannot access ORG_ADMIN endpoint (403 Forbidden)."""
    data = setup_test_orgs_and_users

    emp_token = create_access_token(
        user_id=str(data["user_a_emp"].id),
        organization_id=str(data["org_a"].id),
        organization_slug=data["org_a"].slug,
        role="EMPLOYEE",
    )
    resp = await async_client.get(
        "/test-admin/users",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert resp.status_code == 403
    assert "Operation requires one of the following roles" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_missing_authentication(async_client: AsyncClient):
    """16. Test protected endpoint without Authorization header returns 401."""
    resp = await async_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert "missing" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_rls_enforcement_via_auth_dependency(async_client: AsyncClient, setup_test_orgs_and_users):
    """15 & 17: Test verified auth claims establish transaction-local RLS on the real database."""
    data = setup_test_orgs_and_users

    # Org A creates a confidential document in the DB
    async with SessionLocal() as session:
        doc_a = Document(
            id=uuid.uuid4(),
            organization_id=data["org_a"].id,
            uploaded_by_id=data["user_a_admin"].id,
            title="Alpha Confidential Blueprint",
            file_name="alpha.pdf",
            file_path="/alpha.pdf",
            file_type="PDF",
            file_hash=f"hash-{uuid.uuid4().hex}",
            file_size_bytes=1024,
        )
        session.add(doc_a)
        await session.commit()

    # User B (from Org B) authenticates
    token_b = create_access_token(
        user_id=str(data["user_b"].id),
        organization_id=str(data["org_b"].id),
        organization_slug=data["org_b"].slug,
        role="ORG_ADMIN",
    )

    # User B queries /me
    resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 200
    assert resp.json()["organization_id"] == str(data["org_b"].id)
