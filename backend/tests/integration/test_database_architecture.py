import uuid
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.organization import Organization
from app.models.department import Department
from app.models.user import User
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.document_chunk import DocumentChunk
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.citation import MessageCitation

from sqlalchemy.pool import NullPool

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
APP_USER_TEST_DB_URL = "postgresql+asyncpg://rag_app_user:rag_app_password@127.0.0.1:5434/enterprise_rag_test_db"

test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
app_user_test_engine = create_async_engine(APP_USER_TEST_DB_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)
AppUserSessionLocal = async_sessionmaker(bind=app_user_test_engine, expire_on_commit=False)


@pytest.fixture
async def db_session():
    """Provides a transactional database session rolled back after each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def app_user_session():
    """Provides a session connected as the unprivileged application role (NOBYPASSRLS)."""
    async with AppUserSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.mark.asyncio
async def test_organization_and_department_creation(db_session: AsyncSession):
    """1 & 2: Test creation of Organization and Department entities."""
    org = Organization(
        name="Acme Global Corporation",
        slug=f"acme-{uuid.uuid4().hex[:8]}",
        settings={"domain": "acme.com", "max_docs": 1000},
    )
    db_session.add(org)
    await db_session.flush()

    assert org.id is not None
    assert org.is_active is True

    dept = Department(
        organization_id=org.id,
        name="Artificial Intelligence Research",
        code="AI-RES",
    )
    db_session.add(dept)
    await db_session.flush()

    assert dept.id is not None
    assert dept.organization_id == org.id


@pytest.mark.asyncio
async def test_user_creation_and_unique_constraint(db_session: AsyncSession):
    """3: Test user creation and per-organization email uniqueness constraint."""
    org = Organization(name="FinTech Corp", slug=f"fintech-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    user1 = User(
        organization_id=org.id,
        email="compliance@fintech.com",
        hashed_password="secure-hashed-password",
        full_name="Alice Compliance",
        role="ORG_ADMIN",
    )
    db_session.add(user1)
    await db_session.flush()
    assert user1.id is not None

    # Duplicate email in same org must raise IntegrityError
    user2 = User(
        organization_id=org.id,
        email="compliance@fintech.com",
        hashed_password="another-password",
        full_name="Duplicate Alice",
        role="EMPLOYEE",
    )
    db_session.add(user2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_document_creation(db_session: AsyncSession):
    """4: Test Document creation with SHA-256 hash and metadata."""
    org = Organization(name="DocCorp", slug=f"doccorp-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    user = User(
        organization_id=org.id,
        email="admin@doccorp.com",
        hashed_password="hashed-password",
        full_name="Doc Admin",
        role="KNOWLEDGE_MANAGER",
    )
    db_session.add(user)
    await db_session.flush()

    doc = Document(
        organization_id=org.id,
        uploaded_by_id=user.id,
        title="Employee Security Policy 2026",
        file_name="security_policy.pdf",
        file_path="/storage/docs/security_policy.pdf",
        file_type="PDF",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=1048576,
        status="COMPLETED",
        metadata_={"pages": 12, "author": "Security Team"},
    )
    db_session.add(doc)
    await db_session.flush()

    assert doc.id is not None
    assert doc.status == "COMPLETED"


@pytest.mark.asyncio
async def test_composite_foreign_key_enforcement(db_session: AsyncSession):
    """5 & 6: Test composite foreign key prevents cross-tenant association."""
    # Create Organization A and its document
    org_a = Organization(name="Tenant Alpha", slug=f"alpha-{uuid.uuid4().hex[:8]}")
    org_b = Organization(name="Tenant Beta", slug=f"beta-{uuid.uuid4().hex[:8]}")
    db_session.add_all([org_a, org_b])
    await db_session.flush()

    user_a = User(
        organization_id=org_a.id,
        email="user@alpha.com",
        hashed_password="pw",
        full_name="Alpha User",
    )
    db_session.add(user_a)
    await db_session.flush()

    doc_a = Document(
        organization_id=org_a.id,
        uploaded_by_id=user_a.id,
        title="Alpha Confidential",
        file_name="alpha.pdf",
        file_path="/storage/alpha.pdf",
        file_type="PDF",
        file_hash="hash-alpha-12345",
        file_size_bytes=2048,
    )
    db_session.add(doc_a)
    await db_session.flush()

    # Attempt to create DocumentVersion with Org B referencing Doc from Org A
    # Composite FK (organization_id, document_id) -> documents(organization_id, id) MUST FAIL!
    mismatched_version = DocumentVersion(
        organization_id=org_b.id,  # Mismatched! Belongs to Beta, not Alpha
        document_id=doc_a.id,      # Belongs to Alpha
        version_number=1,
        file_path="/storage/mismatch.pdf",
        file_hash="hash-mismatch",
        file_size_bytes=2048,
        created_by_id=user_a.id,
    )
    db_session.add(mismatched_version)
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    
    assert "fk_doc_versions_org_document" in str(exc_info.value)
    await db_session.rollback()


@pytest.mark.asyncio
async def test_rls_tenant_isolation_with_app_user(app_user_session: AsyncSession):
    """7 & 8: Test PostgreSQL Row Level Security USING and WITH CHECK policies."""
    # Create tenants using privileged session
    org_a_id = uuid.uuid4()
    org_b_id = uuid.uuid4()
    
    async with TestSessionLocal() as super_session:
        org_a = Organization(id=org_a_id, name="RLS Org Alpha", slug=f"rls-a-{org_a_id.hex[:6]}")
        org_b = Organization(id=org_b_id, name="RLS Org Beta", slug=f"rls-b-{org_b_id.hex[:6]}")
        user_a = User(id=uuid.uuid4(), organization_id=org_a_id, email="a@rls.com", hashed_password="pw", full_name="User A")
        user_b = User(id=uuid.uuid4(), organization_id=org_b_id, email="b@rls.com", hashed_password="pw", full_name="User B")
        doc_a = Document(
            id=uuid.uuid4(),
            organization_id=org_a_id,
            uploaded_by_id=user_a.id,
            title="Alpha Secret",
            file_name="alpha.pdf",
            file_path="/p",
            file_type="PDF",
            file_hash="hash-a",
            file_size_bytes=100,
        )
        doc_b = Document(
            id=uuid.uuid4(),
            organization_id=org_b_id,
            uploaded_by_id=user_b.id,
            title="Beta Secret",
            file_name="beta.pdf",
            file_path="/p",
            file_type="PDF",
            file_hash="hash-b",
            file_size_bytes=100,
        )
        super_session.add_all([org_a, org_b, user_a, user_b, doc_a, doc_b])
        await super_session.commit()

    # Now query as rag_app_user (NOBYPASSRLS) with tenant context set to Org A
    await app_user_session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_a_id)},
    )
    result = await app_user_session.execute(select(Document))
    visible_docs = result.scalars().all()

    # MUST only see Org A's document; Org B's document is completely hidden by RLS!
    assert len(visible_docs) == 1
    assert visible_docs[0].organization_id == org_a_id
    assert visible_docs[0].title == "Alpha Secret"

    # Attempt to insert into Org B while context is Org A -> WITH CHECK policy must reject it!
    illegal_doc = Document(
        organization_id=org_b_id,  # Trying to write to Org B!
        uploaded_by_id=user_a.id,
        title="Injected Document",
        file_name="injected.pdf",
        file_path="/p",
        file_type="PDF",
        file_hash="hash-injected",
        file_size_bytes=100,
    )
    app_user_session.add(illegal_doc)
    with pytest.raises(DBAPIError) as exc_info:
        await app_user_session.flush()
    assert "rls_documents_tenant_isolation" in str(exc_info.value) or "check constraint" in str(exc_info.value).lower() or "policy" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_vector_insertion_and_similarity_search(db_session: AsyncSession):
    """9 & 10: Test 1536-dimensional vector embedding insertion and cosine similarity retrieval."""
    org = Organization(name="VectorCorp", slug=f"vector-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    user = User(organization_id=org.id, email="vec@corp.com", hashed_password="pw", full_name="Vec User")
    db_session.add(user)
    await db_session.flush()

    doc = Document(
        organization_id=org.id,
        uploaded_by_id=user.id,
        title="AI Engineering Handbook",
        file_name="ai_handbook.pdf",
        file_path="/docs/ai.pdf",
        file_type="PDF",
        file_hash="ai-hash-999",
        file_size_bytes=5000,
    )
    db_session.add(doc)
    await db_session.flush()

    version = DocumentVersion(
        organization_id=org.id,
        document_id=doc.id,
        version_number=1,
        file_path="/docs/ai.pdf",
        file_hash="ai-hash-999",
        file_size_bytes=5000,
        is_active=True,
        created_by_id=user.id,
    )
    db_session.add(version)
    await db_session.flush()

    # Create dummy 1536-dimensional vectors
    # Vector 1: Highly aligned with direction [1.0, 0.0, ...]
    v1 = [1.0] + [0.0] * 1535
    # Vector 2: Partially aligned with direction [0.5, 0.5, ...]
    v2 = [0.5, 0.5] + [0.0] * 1534
    # Vector 3: Orthogonal direction [0.0, 1.0, ...]
    v3 = [0.0, 1.0] + [0.0] * 1534

    chunk1 = DocumentChunk(
        organization_id=org.id,
        document_id=doc.id,
        version_id=version.id,
        chunk_index=0,
        content="Retrieval-Augmented Generation architectures use vector databases for grounded context.",
        token_count=12,
        embedding=v1,
        is_active=True,
    )
    chunk2 = DocumentChunk(
        organization_id=org.id,
        document_id=doc.id,
        version_id=version.id,
        chunk_index=1,
        content="Vector databases index embeddings using Hierarchical Navigable Small World graphs.",
        token_count=11,
        embedding=v2,
        is_active=True,
    )
    chunk3 = DocumentChunk(
        organization_id=org.id,
        document_id=doc.id,
        version_id=version.id,
        chunk_index=2,
        content="PostgreSQL full-text search provides keyword search through tsvector and GIN indexes.",
        token_count=11,
        embedding=v3,
        is_active=True,
    )
    db_session.add_all([chunk1, chunk2, chunk3])
    await db_session.flush()

    # Query vector close to vector 1: [0.99, 0.01, 0, 0, ...]
    query_vector = [0.99, 0.01] + [0.0] * 1534

    # Perform cosine similarity search using pgvector's cosine distance operator <=>
    stmt = (
        select(
            DocumentChunk.content,
            DocumentChunk.chunk_index,
            DocumentChunk.embedding.cosine_distance(query_vector).label("distance"),
        )
        .where(
            DocumentChunk.organization_id == org.id,
            DocumentChunk.is_active.is_(True),
        )
        .order_by("distance")
        .limit(2)
    )
    results = (await db_session.execute(stmt)).all()

    assert len(results) == 2
    # Nearest neighbor must be chunk 1 (lowest cosine distance)
    assert results[0].chunk_index == 0
    assert results[0].distance < results[1].distance


@pytest.mark.asyncio
async def test_document_versioning_lifecycle(db_session: AsyncSession):
    """11: Test DocumentVersion lifecycle, active version switching, and chunk segregation."""
    org = Organization(name="Versioned Org", slug=f"ver-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    user = User(organization_id=org.id, email="editor@org.com", hashed_password="pw", full_name="Editor")
    db_session.add(user)
    await db_session.flush()

    doc = Document(
        organization_id=org.id,
        uploaded_by_id=user.id,
        title="Company Handbook",
        file_name="handbook.pdf",
        file_path="/storage/handbook_v1.pdf",
        file_type="PDF",
        file_hash="hash-handbook-v1",
        file_size_bytes=1000,
    )
    db_session.add(doc)
    await db_session.flush()

    # Version 1
    v1 = DocumentVersion(
        organization_id=org.id,
        document_id=doc.id,
        version_number=1,
        file_path="/storage/handbook_v1.pdf",
        file_hash="hash-handbook-v1",
        file_size_bytes=1000,
        is_active=False,  # Replaced by V2
        change_summary="Initial release",
        created_by_id=user.id,
    )
    # Version 2
    v2 = DocumentVersion(
        organization_id=org.id,
        document_id=doc.id,
        version_number=2,
        file_path="/storage/handbook_v2.pdf",
        file_hash="hash-handbook-v2",
        file_size_bytes=1200,
        is_active=True,  # Active version
        change_summary="Updated 2026 remote work policy",
        created_by_id=user.id,
    )
    db_session.add_all([v1, v2])
    await db_session.flush()

    dummy_vec = [0.1] * 1536
    # Chunk belonging to V1 (outdated)
    c1 = DocumentChunk(
        organization_id=org.id,
        document_id=doc.id,
        version_id=v1.id,
        chunk_index=0,
        content="2024 Policy: All employees must work from office.",
        token_count=10,
        embedding=dummy_vec,
        is_active=False,
    )
    # Chunk belonging to V2 (current)
    c2 = DocumentChunk(
        organization_id=org.id,
        document_id=doc.id,
        version_id=v2.id,
        chunk_index=0,
        content="2026 Policy: Hybrid and remote options are supported.",
        token_count=10,
        embedding=dummy_vec,
        is_active=True,
    )
    db_session.add_all([c1, c2])
    await db_session.flush()

    # Query for retrieval using active version filter
    active_chunks = (
        await db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.is_active.is_(True),
            )
        )
    ).scalars().all()

    assert len(active_chunks) == 1
    assert "2026 Policy" in active_chunks[0].content
    assert active_chunks[0].version_id == v2.id


@pytest.mark.asyncio
async def test_database_cascade_behavior(db_session: AsyncSession):
    """12: Test ON DELETE CASCADE removes versions, chunks, and citations automatically."""
    org = Organization(name="Ephemeral Corp", slug=f"ephemeral-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    await db_session.flush()

    user = User(organization_id=org.id, email="ephemeral@org.com", hashed_password="pw", full_name="User")
    db_session.add(user)
    await db_session.flush()

    doc = Document(
        organization_id=org.id,
        uploaded_by_id=user.id,
        title="Temporary Document",
        file_name="temp.pdf",
        file_path="/storage/temp.pdf",
        file_type="PDF",
        file_hash="temp-hash-001",
        file_size_bytes=500,
    )
    db_session.add(doc)
    await db_session.flush()

    ver = DocumentVersion(
        organization_id=org.id,
        document_id=doc.id,
        version_number=1,
        file_path="/storage/temp.pdf",
        file_hash="temp-hash-001",
        file_size_bytes=500,
        is_active=True,
        created_by_id=user.id,
    )
    db_session.add(ver)
    await db_session.flush()

    chunk = DocumentChunk(
        organization_id=org.id,
        document_id=doc.id,
        version_id=ver.id,
        chunk_index=0,
        content="Temporary knowledge chunk",
        token_count=5,
        embedding=[0.05] * 1536,
        is_active=True,
    )
    db_session.add(chunk)
    await db_session.flush()

    # Delete Document -> should cascade to DocumentVersion and DocumentChunk
    await db_session.delete(doc)
    await db_session.flush()

    remaining_versions = (
        await db_session.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))
    ).scalars().all()
    remaining_chunks = (
        await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    ).scalars().all()

    assert len(remaining_versions) == 0
    assert len(remaining_chunks) == 0
