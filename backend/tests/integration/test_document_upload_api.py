import io
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.department import Department
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.organization import Organization
from app.models.user import User
from app.services.storage import get_storage_provider
from app.services.storage.local import LocalStorageProvider

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


def create_sample_pdf_bytes() -> bytes:
    """Generates minimal syntactically conforming PDF byte sequence."""
    return b"%PDF-1.7\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF\n"


def create_sample_docx_bytes() -> bytes:
    """Generates in-memory valid OpenXML DOCX archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        zf.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Sample DOCX</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


@pytest.fixture
def temp_test_storage():
    """Configures an isolated temporary storage directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="rag_test_storage_api_")
    storage_provider = LocalStorageProvider(base_dir=temp_dir)
    app.dependency_overrides[get_storage_provider] = lambda: storage_provider

    yield storage_provider, Path(temp_dir)

    app.dependency_overrides.pop(get_storage_provider, None)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def setup_upload_tenants():
    """Seeds test organizations, departments, and users in PostgreSQL."""
    async with SessionLocal() as session:
        # Organization A
        org_a = Organization(
            id=uuid.uuid4(),
            name="Alpha Corp",
            slug=f"alpha-upload-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        # Organization B
        org_b = Organization(
            id=uuid.uuid4(),
            name="Beta Corp",
            slug=f"beta-upload-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add_all([org_a, org_b])
        await session.flush()

        # Departments
        dept_a = Department(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            name="Engineering",
            code=f"eng-{uuid.uuid4().hex[:4]}",
        )
        dept_b = Department(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            name="Marketing",
            code=f"mkt-{uuid.uuid4().hex[:4]}",
        )
        session.add_all([dept_a, dept_b])
        await session.flush()

        pw_hash = get_password_hash("Secret123!")

        # Org A Admin (Knowledge Manager / Admin role)
        admin_a = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            department_id=dept_a.id,
            email="admin@alpha.com",
            hashed_password=pw_hash,
            full_name="Alice Admin",
            role="ORG_ADMIN",
            is_active=True,
        )
        # Org A Employee (Cannot upload)
        employee_a = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            department_id=dept_a.id,
            email="employee@alpha.com",
            hashed_password=pw_hash,
            full_name="Bob Employee",
            role="EMPLOYEE",
            is_active=True,
        )
        # Org B Admin
        admin_b = User(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            department_id=dept_b.id,
            email="admin@beta.com",
            hashed_password=pw_hash,
            full_name="Charlie Beta",
            role="ORG_ADMIN",
            is_active=True,
        )
        session.add_all([admin_a, employee_a, admin_b])
        await session.commit()

        # Auth tokens
        token_a_admin = create_access_token(
            user_id=str(admin_a.id),
            organization_id=str(org_a.id),
            organization_slug=org_a.slug,
            role=admin_a.role,
        )
        token_a_emp = create_access_token(
            user_id=str(employee_a.id),
            organization_id=str(org_a.id),
            organization_slug=org_a.slug,
            role=employee_a.role,
        )
        token_b_admin = create_access_token(
            user_id=str(admin_b.id),
            organization_id=str(org_b.id),
            organization_slug=org_b.slug,
            role=admin_b.role,
        )

        return {
            "org_a": org_a,
            "org_b": org_b,
            "dept_a": dept_a,
            "dept_b": dept_b,
            "admin_a": admin_a,
            "employee_a": employee_a,
            "admin_b": admin_b,
            "token_a_admin": token_a_admin,
            "token_a_emp": token_a_emp,
            "token_b_admin": token_b_admin,
        }


@pytest.mark.asyncio
async def test_successful_pdf_upload(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """1, 17, 18: Test successful PDF upload creates Document, DocumentVersion (v1), and IngestionJob (QUEUED)."""
    data = setup_upload_tenants
    storage, _ = temp_test_storage
    pdf_bytes = create_sample_pdf_bytes()

    files = {"file": ("architecture_blueprint.pdf", pdf_bytes, "application/pdf")}
    data_form = {
        "title": "System Architecture Blueprint",
        "department_id": str(data["dept_a"].id),
    }

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        data=data_form,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "System Architecture Blueprint"
    assert body["file_type"] == "PDF"
    assert body["status"] == "UPLOADED"
    assert body["file_size_bytes"] == len(pdf_bytes)
    assert body["organization_id"] == str(data["org_a"].id)
    assert body["department_id"] == str(data["dept_a"].id)

    doc_id = uuid.UUID(body["document_id"])
    version_id = uuid.UUID(body["version_id"])
    job_id = uuid.UUID(body["job_id"])

    # Verify directly in real PostgreSQL database
    async with SessionLocal() as session:
        # Check Document
        doc = await session.get(Document, doc_id)
        assert doc is not None
        assert doc.status == "UPLOADED"
        assert doc.current_version_id == version_id

        # Check DocumentVersion (Task 17)
        ver = await session.get(DocumentVersion, version_id)
        assert ver is not None
        assert ver.version_number == 1
        assert ver.is_active is True
        assert ver.file_size_bytes == len(pdf_bytes)

        # Check IngestionJob (Task 18)
        job = await session.get(IngestionJob, job_id)
        assert job is not None
        assert job.status == "QUEUED"
        assert job.document_id == doc_id
        assert job.version_id == version_id

        # Verify physical file exists in storage engine
        assert await storage.exists(doc.file_path) is True


@pytest.mark.asyncio
async def test_successful_docx_upload(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """2: Test successful DOCX upload with deep OpenXML inspection."""
    data = setup_upload_tenants
    docx_bytes = create_sample_docx_bytes()

    files = {"file": ("onboarding_handbook.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["file_type"] == "DOCX"
    assert body["file_name"] == "onboarding_handbook.docx"
    assert body["status"] == "UPLOADED"


@pytest.mark.asyncio
async def test_invalid_file_extension(
    async_client: AsyncClient,
    setup_upload_tenants,
):
    """3: Test upload with unsupported extension is rejected (400 Bad Request)."""
    data = setup_upload_tenants
    files = {"file": ("danger.exe", b"MZ executable bytes", "application/octet-stream")}

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 400
    assert "not permitted" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_incorrect_file_signature(
    async_client: AsyncClient,
    setup_upload_tenants,
):
    """4 & 5: Test file with declared .pdf extension but garbage signature is rejected."""
    data = setup_upload_tenants
    # Fake PDF content (does NOT start with %PDF-)
    fake_pdf = b"This is just plain text disguised as a PDF file."
    files = {"file": ("disguised.pdf", fake_pdf, "application/pdf")}

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 400
    assert "magic signature" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_empty_file_rejection(
    async_client: AsyncClient,
    setup_upload_tenants,
):
    """6: Test empty file (0 bytes) is rejected."""
    data = setup_upload_tenants
    files = {"file": ("empty.pdf", b"", "application/pdf")}

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 400
    assert "empty" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_max_file_size_enforcement(
    async_client: AsyncClient,
    setup_upload_tenants,
    monkeypatch,
):
    """7: Test oversized file upload rejection."""
    data = setup_upload_tenants

    # Set temporary low max size: 50 bytes
    from app.core import config
    settings = config.get_settings()
    monkeypatch.setattr(settings, "MAX_UPLOAD_FILE_SIZE_BYTES", 50)

    # 100 bytes of valid PDF
    oversized_pdf = b"%PDF-1.7" + b"X" * 100
    files = {"file": ("oversized.pdf", oversized_pdf, "application/pdf")}

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 400
    assert "exceeds maximum permitted limit" in resp.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_file_upload_rejected(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """8: Test identical file upload to same organization returns 409 Conflict with details."""
    data = setup_upload_tenants
    storage, _ = temp_test_storage
    pdf_bytes = create_sample_pdf_bytes()

    # First upload: Success
    files1 = {"file": ("original.pdf", pdf_bytes, "application/pdf")}
    resp1 = await async_client.post(
        "/api/v1/documents/upload",
        files=files1,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp1.status_code == 201
    initial_doc_id = resp1.json()["document_id"]

    # Second upload with different filename but identical bytes: 409 Conflict
    files2 = {"file": ("copy_of_original.pdf", pdf_bytes, "application/pdf")}
    resp2 = await async_client.post(
        "/api/v1/documents/upload",
        files=files2,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp2.status_code == 409
    err = resp2.json()["error"]
    assert "identical cryptographic fingerprint" in err["message"].lower()
    assert err["details"]["existing_document_id"] == initial_doc_id


@pytest.mark.asyncio
async def test_duplicate_allowed_in_different_organization(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """8b: Test identical file hash IS allowed across two DIFFERENT organizations."""
    data = setup_upload_tenants
    pdf_bytes = create_sample_pdf_bytes()

    # Upload to Org A
    files_a = {"file": ("shared_spec.pdf", pdf_bytes, "application/pdf")}
    resp_a = await async_client.post(
        "/api/v1/documents/upload",
        files=files_a,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp_a.status_code == 201

    # Upload same file to Org B: Must succeed!
    files_b = {"file": ("shared_spec.pdf", pdf_bytes, "application/pdf")}
    resp_b = await async_client.post(
        "/api/v1/documents/upload",
        files=files_b,
        headers={"Authorization": f"Bearer {data['token_b_admin']}"},
    )
    assert resp_b.status_code == 201
    assert resp_b.json()["organization_id"] == str(data["org_b"].id)


@pytest.mark.asyncio
async def test_unauthorized_upload(async_client: AsyncClient):
    """10: Test upload without Authorization header returns 401."""
    files = {"file": ("test.pdf", create_sample_pdf_bytes(), "application/pdf")}
    resp = await async_client.post("/api/v1/documents/upload", files=files)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_employee_upload_rejected(
    async_client: AsyncClient,
    setup_upload_tenants,
):
    """11: Test user with EMPLOYEE role cannot upload (403 Forbidden)."""
    data = setup_upload_tenants
    files = {"file": ("test.pdf", create_sample_pdf_bytes(), "application/pdf")}

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_emp']}"},
    )
    assert resp.status_code == 403
    assert "documents:upload" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_department_ownership_validation(
    async_client: AsyncClient,
    setup_upload_tenants,
):
    """13: Test providing department_id from another organization is rejected."""
    data = setup_upload_tenants
    files = {"file": ("test.pdf", create_sample_pdf_bytes(), "application/pdf")}

    # Org A Admin tries to assign document to Org B's department!
    form_data = {"department_id": str(data["dept_b"].id)}

    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        data=form_data,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 400
    assert "does not exist or does not belong to your organization" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_cross_tenant_document_isolation(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """12: Test Org B cannot view or delete documents belonging to Org A."""
    data = setup_upload_tenants
    files = {"file": ("org_a_private.pdf", create_sample_pdf_bytes(), "application/pdf")}

    # Org A uploads document
    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 201
    doc_a_id = resp.json()["document_id"]

    # Org B attempts GET /documents/{doc_a_id}
    get_resp = await async_client.get(
        f"/api/v1/documents/{doc_a_id}",
        headers={"Authorization": f"Bearer {data['token_b_admin']}"},
    )
    # RLS & Scoping ensure 404 EntityNotFound
    assert get_resp.status_code == 404

    # Org B attempts DELETE /documents/{doc_a_id}
    del_resp = await async_client.delete(
        f"/api/v1/documents/{doc_a_id}",
        headers={"Authorization": f"Bearer {data['token_b_admin']}"},
    )
    assert del_resp.status_code == 404


@pytest.mark.asyncio
async def test_document_deletion_and_storage_cleanup(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """19: Test document deletion removes DB records and cleans up stored files."""
    data = setup_upload_tenants
    storage, _ = temp_test_storage

    # Upload
    files = {"file": ("to_delete.pdf", create_sample_pdf_bytes(), "application/pdf")}
    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    doc_id = resp.json()["document_id"]

    # Fetch document to obtain storage key
    async with SessionLocal() as session:
        doc = await session.get(Document, uuid.UUID(doc_id))
        storage_key = doc.file_path
        assert await storage.exists(storage_key) is True

    # Delete via API
    del_resp = await async_client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Verify deleted from DB
    async with SessionLocal() as session:
        doc_after = await session.get(Document, uuid.UUID(doc_id))
        assert doc_after is None

    # Verify physical file is deleted from storage
    assert await storage.exists(storage_key) is False


@pytest.mark.asyncio
async def test_document_list_and_status(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """Test listing documents and polling document status."""
    data = setup_upload_tenants

    # Upload
    files = {"file": ("status_test.pdf", create_sample_pdf_bytes(), "application/pdf")}
    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    doc_id = resp.json()["document_id"]

    # 1. List
    list_resp = await async_client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) >= 1
    assert any(item["id"] == doc_id for item in items)

    # 2. Status
    status_resp = await async_client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["document_status"] == "UPLOADED"
    assert status_body["job_status"] == "QUEUED"


@pytest.mark.asyncio
async def test_storage_provider_failure_compensating_rollback(
    async_client: AsyncClient,
    setup_upload_tenants,
    monkeypatch,
):
    """14: Test storage provider failure aborts process without creating database records."""
    data = setup_upload_tenants

    from app.services.storage.local import LocalStorageProvider

    async def _failing_save(*args, **kwargs):
        raise IOError("Disk full or I/O failure on storage volume")

    monkeypatch.setattr(LocalStorageProvider, "save", _failing_save)

    files = {"file": ("io_fail.pdf", create_sample_pdf_bytes(), "application/pdf")}
    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 500

    # Ensure no orphan document record exists in DB
    async with SessionLocal() as session:
        stmt = select(Document).where(Document.title == "io_fail")
        res = await session.execute(stmt)
        assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_database_rollback_compensating_storage_cleanup(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
    monkeypatch,
):
    """15 & 16: Test that when database commit fails, compensating cleanup deletes the staged storage file."""
    data = setup_upload_tenants
    storage, _ = temp_test_storage

    # Intercept session.flush to simulate a database failure
    from sqlalchemy.ext.asyncio import AsyncSession
    original_flush = AsyncSession.flush

    async def _failing_flush(self, *args, **kwargs):
        # Fail when inserting document
        raise RuntimeError("Simulated database crash during flush")

    monkeypatch.setattr(AsyncSession, "flush", _failing_flush)

    files = {"file": ("db_fail.pdf", create_sample_pdf_bytes(), "application/pdf")}
    resp = await async_client.post(
        "/api/v1/documents/upload",
        files=files,
        headers={"Authorization": f"Bearer {data['token_a_admin']}"},
    )
    assert resp.status_code == 500

    # Verify that NO files remain in storage directory (compensating cleanup succeeded)
    stored_files = list(storage.base_dir.rglob("*.pdf"))
    assert len(stored_files) == 0


@pytest.mark.asyncio
async def test_simultaneous_duplicate_uploads(
    async_client: AsyncClient,
    setup_upload_tenants,
    temp_test_storage,
):
    """9: Test simultaneous/concurrent duplicate upload handling."""
    import asyncio
    data = setup_upload_tenants
    pdf_bytes = create_sample_pdf_bytes()

    # Launch two concurrent upload requests with identical content
    async def _do_upload(name: str):
        return await async_client.post(
            "/api/v1/documents/upload",
            files={"file": (name, pdf_bytes, "application/pdf")},
            headers={"Authorization": f"Bearer {data['token_a_admin']}"},
        )

    res_1, res_2 = await asyncio.gather(_do_upload("first.pdf"), _do_upload("second.pdf"))

    statuses = {res_1.status_code, res_2.status_code}
    # One must succeed (201) and the other must be rejected (409 Conflict)
    assert 201 in statuses
    assert 409 in statuses

    # Verify exactly one document exists in DB for this hash
    async with SessionLocal() as session:
        import hashlib
        computed_hash = hashlib.sha256(pdf_bytes).hexdigest()
        stmt = select(Document).where(
            Document.organization_id == data["org_a"].id,
            Document.file_hash == computed_hash,
        )
        res = await session.execute(stmt)
        docs = res.scalars().all()
        assert len(docs) == 1
