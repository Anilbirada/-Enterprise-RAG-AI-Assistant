import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token, get_password_hash
from app.models.department import Department
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.organization import Organization
from app.models.user import User
from app.repositories.vector_repository import VectorRepository
from app.schemas.chunk import ChunkMetadata, DocumentChunkData
from app.services.embedding_service import EmbeddingService

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
async def setup_search_tenants():
    """Seeds test tenants, departments, users, documents, and chunks in PostgreSQL."""
    embedder = EmbeddingService(api_key=None, dimensions=1536)

    async with SessionLocal() as session:
        # Organization Alpha
        org_a = Organization(
            id=uuid.uuid4(),
            name="Search Alpha Corp",
            slug=f"alpha-search-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        # Organization Beta (Tenant isolation)
        org_b = Organization(
            id=uuid.uuid4(),
            name="Search Beta Corp",
            slug=f"beta-search-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add_all([org_a, org_b])
        await session.flush()

        # Department in Alpha
        dept_eng = Department(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            name="Engineering",
            code=f"eng-{uuid.uuid4().hex[:4]}",
        )
        dept_hr = Department(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            name="Human Resources",
            code=f"hr-{uuid.uuid4().hex[:4]}",
        )
        session.add_all([dept_eng, dept_hr])
        await session.flush()

        pw_hash = get_password_hash("SearchPassword123!")

        user_a = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            department_id=dept_eng.id,
            email=f"alice-{uuid.uuid4().hex[:4]}@alpha.com",
            hashed_password=pw_hash,
            full_name="Alice Engineer",
            role="EMPLOYEE",  # Employees have Permission.VIEW_DOCUMENTS
            is_active=True,
        )
        user_b = User(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            email=f"bob-{uuid.uuid4().hex[:4]}@beta.com",
            hashed_password=pw_hash,
            full_name="Bob Beta",
            role="EMPLOYEE",
            is_active=True,
        )
        session.add_all([user_a, user_b])
        await session.flush()

        # Document 1 (Engineering - Alpha)
        doc_eng_id = uuid.uuid4()
        ver_eng_id = uuid.uuid4()
        doc_eng = Document(
            id=doc_eng_id,
            organization_id=org_a.id,
            department_id=dept_eng.id,
            uploaded_by_id=user_a.id,
            title="FastAPI & PostgreSQL Architecture",
            file_name="fastapi_postgres.pdf",
            file_path="storage/fastapi_postgres.pdf",
            file_type="PDF",
            file_size_bytes=1000,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="COMPLETED",
            current_version_id=ver_eng_id,
        )
        ver_eng = DocumentVersion(
            id=ver_eng_id,
            organization_id=org_a.id,
            document_id=doc_eng_id,
            version_number=1,
            file_size_bytes=1000,
            file_hash=doc_eng.file_hash,
            file_path=doc_eng.file_path,
            created_by_id=user_a.id,
            is_active=True,
        )

        # Document 2 (HR - Alpha)
        doc_hr_id = uuid.uuid4()
        ver_hr_id = uuid.uuid4()
        doc_hr = Document(
            id=doc_hr_id,
            organization_id=org_a.id,
            department_id=dept_hr.id,
            uploaded_by_id=user_a.id,
            title="Employee Vacation & Benefits Policy",
            file_name="vacation_benefits.pdf",
            file_path="storage/vacation_benefits.pdf",
            file_type="PDF",
            file_size_bytes=800,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="COMPLETED",
            current_version_id=ver_hr_id,
        )
        ver_hr = DocumentVersion(
            id=ver_hr_id,
            organization_id=org_a.id,
            document_id=doc_hr_id,
            version_number=1,
            file_size_bytes=800,
            file_hash=doc_hr.file_hash,
            file_path=doc_hr.file_path,
            created_by_id=user_a.id,
            is_active=True,
        )

        # Document 3 (Beta Corp document with similar content)
        doc_b_id = uuid.uuid4()
        ver_b_id = uuid.uuid4()
        doc_b = Document(
            id=doc_b_id,
            organization_id=org_b.id,
            uploaded_by_id=user_b.id,
            title="Beta Confidential Architecture",
            file_name="beta_arch.pdf",
            file_path="storage/beta_arch.pdf",
            file_type="PDF",
            file_size_bytes=500,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="COMPLETED",
            current_version_id=ver_b_id,
        )
        ver_b = DocumentVersion(
            id=ver_b_id,
            organization_id=org_b.id,
            document_id=doc_b_id,
            version_number=1,
            file_size_bytes=500,
            file_hash=doc_b.file_hash,
            file_path=doc_b.file_path,
            created_by_id=user_b.id,
            is_active=True,
        )

        session.add_all([doc_eng, ver_eng, doc_hr, ver_hr, doc_b, ver_b])
        await session.flush()

        # Seed Chunks for Engineering Doc
        eng_text_1 = "PostgreSQL 16 with pgvector extension powers enterprise semantic vector retrieval."
        eng_text_2 = "FastAPI provides asynchronous request routing and strict Pydantic model validation."
        chunks_eng = [
            DocumentChunkData(
                content=eng_text_1,
                embedding=embedder._generate_mock_vector(eng_text_1),
                metadata=ChunkMetadata(
                    document_id=doc_eng_id,
                    version_id=ver_eng_id,
                    organization_id=org_a.id,
                    chunk_index=0,
                    page_number=1,
                    token_count=12,
                    char_count=len(eng_text_1),
                    section_title="Database",
                ),
            ),
            DocumentChunkData(
                content=eng_text_2,
                embedding=embedder._generate_mock_vector(eng_text_2),
                metadata=ChunkMetadata(
                    document_id=doc_eng_id,
                    version_id=ver_eng_id,
                    organization_id=org_a.id,
                    chunk_index=1,
                    page_number=1,
                    token_count=11,
                    char_count=len(eng_text_2),
                    section_title="Backend",
                ),
            ),
        ]

        # Seed Chunks for HR Doc
        hr_text = "All full-time employees accrue 25 paid vacation days per calendar year."
        chunks_hr = [
            DocumentChunkData(
                content=hr_text,
                embedding=embedder._generate_mock_vector(hr_text),
                metadata=ChunkMetadata(
                    document_id=doc_hr_id,
                    version_id=ver_hr_id,
                    organization_id=org_a.id,
                    chunk_index=0,
                    page_number=1,
                    token_count=13,
                    char_count=len(hr_text),
                    section_title="PTO Policy",
                ),
            )
        ]

        # Seed Chunks for Beta Doc
        beta_text = "PostgreSQL pgvector is also used at Beta Corp for proprietary experiments."
        chunks_beta = [
            DocumentChunkData(
                content=beta_text,
                embedding=embedder._generate_mock_vector(beta_text),
                metadata=ChunkMetadata(
                    document_id=doc_b_id,
                    version_id=ver_b_id,
                    organization_id=org_b.id,
                    chunk_index=0,
                    page_number=1,
                    token_count=12,
                    char_count=len(beta_text),
                ),
            )
        ]

        await VectorRepository.batch_insert_chunks(session, chunks_eng)
        await VectorRepository.batch_insert_chunks(session, chunks_hr)
        await VectorRepository.batch_insert_chunks(session, chunks_beta)
        await session.commit()

        # Generate tokens
        token_a = create_access_token(
            user_id=str(user_a.id),
            organization_id=str(org_a.id),
            organization_slug=org_a.slug,
            role=user_a.role,
            department_id=str(user_a.department_id) if user_a.department_id else None,
        )
        token_b = create_access_token(
            user_id=str(user_b.id),
            organization_id=str(org_b.id),
            organization_slug=org_b.slug,
            role=user_b.role,
        )

        return {
            "org_a": org_a,
            "org_b": org_b,
            "dept_eng": dept_eng,
            "dept_hr": dept_hr,
            "user_a": user_a,
            "user_b": user_b,
            "token_a": token_a,
            "token_b": token_b,
            "doc_eng_id": doc_eng_id,
            "doc_hr_id": doc_hr_id,
        }


@pytest.mark.asyncio
async def test_semantic_search_endpoint(async_client: AsyncClient, setup_search_tenants):
    """1. Test POST /api/v1/search/semantic returns relevant dense vector matches."""
    data = setup_search_tenants
    token_a = data["token_a"]

    resp = await async_client.post(
        "/api/v1/search/semantic",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "query": "PostgreSQL 16 with pgvector extension powers enterprise semantic vector retrieval.",
            "limit": 5,
        },
    )

    assert resp.status_code == 200
    body = resp.json()

    assert body["retrieval_method"] == "DENSE"
    assert body["total_candidates"] >= 1
    assert body["execution_time_ms"] > 0
    assert len(body["results"]) >= 1

    top_result = body["results"][0]
    assert "pgvector" in top_result["content"]
    assert top_result["organization_id"] == str(data["org_a"].id)
    assert top_result["score"] > 0.9  # Identical query text produces score ~ 1.0


@pytest.mark.asyncio
async def test_hybrid_search_endpoint(async_client: AsyncClient, setup_search_tenants):
    """2. Test POST /api/v1/search/hybrid combines dense and sparse search with RRF."""
    data = setup_search_tenants
    token_a = data["token_a"]

    resp = await async_client.post(
        "/api/v1/search/hybrid",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "query": "FastAPI asynchronous request routing",
            "limit": 5,
            "dense_weight": 0.7,
            "sparse_weight": 0.3,
            "rrf_k": 60,
        },
    )

    assert resp.status_code == 200
    body = resp.json()

    assert body["retrieval_method"] == "HYBRID"
    assert body["total_candidates"] >= 1
    assert len(body["results"]) >= 1

    top_chunk = body["results"][0]
    assert "FastAPI" in top_chunk["content"]
    assert top_chunk["score"] > 0
    assert top_chunk["metadata"]["fusion_method"] == "RRF"


@pytest.mark.asyncio
async def test_search_multi_tenant_isolation(async_client: AsyncClient, setup_search_tenants):
    """3. Test that queries by User Beta NEVER return chunks belonging to Organization Alpha."""
    data = setup_search_tenants
    token_b = data["token_b"]

    # Beta searches for "pgvector"
    resp = await async_client.post(
        "/api/v1/search/hybrid",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"query": "pgvector", "limit": 10},
    )

    assert resp.status_code == 200
    body = resp.json()

    # Must only contain Beta Corp chunks
    for result in body["results"]:
        assert result["organization_id"] == str(data["org_b"].id)
        assert "Beta Corp" in result["content"]
        assert "Alpha" not in result["content"]


@pytest.mark.asyncio
async def test_search_department_filtering(async_client: AsyncClient, setup_search_tenants):
    """4. Test department filtering restricts search results to the designated department."""
    data = setup_search_tenants
    token_a = data["token_a"]
    dept_hr_id = data["dept_hr"].id
    doc_hr_id = data["doc_hr_id"]

    resp = await async_client.post(
        "/api/v1/search/semantic",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "query": "vacation benefits policy",
            "department_id": str(dept_hr_id),
            "limit": 5,
        },
    )

    assert resp.status_code == 200
    body = resp.json()

    assert len(body["results"]) == 1
    assert body["results"][0]["document_id"] == str(doc_hr_id)
    assert "vacation days" in body["results"][0]["content"]


@pytest.mark.asyncio
async def test_search_unauthenticated(async_client: AsyncClient):
    """5. Test unauthenticated search request is rejected with 401."""
    resp = await async_client.post(
        "/api/v1/search/semantic",
        json={"query": "unauthorized query"},
    )
    assert resp.status_code == 401
