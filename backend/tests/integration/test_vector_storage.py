import io
import shutil
import tempfile
import uuid
import docx
import pymupdf as fitz
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.core.security import get_password_hash
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.organization import Organization
from app.models.user import User
from app.repositories.vector_repository import VectorRepository
from app.schemas.chunk import ChunkMetadata, DocumentChunkData
from app.services.chunking_embedding_pipeline import ChunkingAndEmbeddingPipeline
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.storage.local import LocalStorageProvider

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
async def setup_vector_records():
    """Seeds test organizations and users in PostgreSQL."""
    async with SessionLocal() as session:
        # Organization Alpha
        org_a = Organization(
            id=uuid.uuid4(),
            name="Alpha Corp",
            slug=f"alpha-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        # Organization Beta (for multi-tenant isolation testing)
        org_b = Organization(
            id=uuid.uuid4(),
            name="Beta Corp",
            slug=f"beta-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add_all([org_a, org_b])
        await session.flush()

        user_a = User(
            id=uuid.uuid4(),
            organization_id=org_a.id,
            email=f"alpha-user-{uuid.uuid4().hex[:4]}@alpha.com",
            hashed_password=get_password_hash("Password123!"),
            full_name="Alpha User",
            role="ORG_ADMIN",
            is_active=True,
        )
        user_b = User(
            id=uuid.uuid4(),
            organization_id=org_b.id,
            email=f"beta-user-{uuid.uuid4().hex[:4]}@beta.com",
            hashed_password=get_password_hash("Password123!"),
            full_name="Beta User",
            role="ORG_ADMIN",
            is_active=True,
        )
        session.add_all([user_a, user_b])
        await session.commit()

        return {
            "org_a": org_a,
            "org_b": org_b,
            "user_a": user_a,
            "user_b": user_b,
        }


@pytest.mark.asyncio
async def test_batch_insert_and_tsvector_generation(setup_vector_records):
    """1. Test batch vector insertion and automatic tsvector generated column population."""
    data = setup_vector_records
    org = data["org_a"]
    user = data["user_a"]

    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=org.id,
            uploaded_by_id=user.id,
            title="Database Architecture Guide",
            file_name="db_arch.pdf",
            file_path="storage/key/db_arch.pdf",
            file_type="PDF",
            file_size_bytes=1024,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        ver = DocumentVersion(
            id=ver_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=1024,
            file_hash=doc.file_hash,
            file_path="storage/key/db_arch.pdf",
            created_by_id=user.id,
        )
        session.add_all([doc, ver])
        await session.commit()

    # Create 3 chunks with 1536-dimensional embeddings
    v1 = [1.0] + [0.0] * 1535
    v2 = [0.0, 1.0] + [0.0] * 1534

    chunk_data = [
        DocumentChunkData(
            content="PostgreSQL with pgvector extension enables scalable vector similarity indexing.",
            embedding=v1,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=0,
                page_number=1,
                token_count=12,
                char_count=80,
                has_table=False,
                section_title="Overview",
            ),
        ),
        DocumentChunkData(
            content="Hierarchical Navigable Small World (HNSW) graphs offer logarithmic search latency.",
            embedding=v2,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=1,
                page_number=2,
                token_count=13,
                char_count=83,
                has_table=True,
                section_title="Algorithms",
            ),
        ),
    ]

    async with SessionLocal() as session:
        inserted = await VectorRepository.batch_insert_chunks(
            session=session,
            chunks=chunk_data,
            is_active=True,
        )
        await session.commit()
        assert len(inserted) == 2

    # Verify rows in database
    async with SessionLocal() as session:
        chunks = await VectorRepository.get_chunks_by_document(
            session=session,
            organization_id=org.id,
            document_id=doc_id,
        )
        assert len(chunks) == 2
        assert chunks[0].chunk_index == 0
        assert chunks[0].token_count == 12
        assert chunks[0].metadata_["section_title"] == "Overview"
        assert chunks[0].metadata_["has_table"] is False

        assert chunks[1].chunk_index == 1
        assert chunks[1].metadata_["has_table"] is True

        # Verify tsvector was automatically generated by PostgreSQL
        stmt = select(DocumentChunk.search_vector).where(DocumentChunk.id == chunks[0].id)
        res = await session.execute(stmt)
        search_vec = res.scalar_one()
        assert search_vec is not None
        assert "postgresql" in str(search_vec)
        assert "pgvector" in str(search_vec)


@pytest.mark.asyncio
async def test_vector_similarity_search_and_thresholding(setup_vector_records):
    """2. Test cosine similarity search, nearest neighbor ranking, and threshold filtering."""
    data = setup_vector_records
    org = data["org_a"]
    user = data["user_a"]

    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=org.id,
            uploaded_by_id=user.id,
            title="Similarity Guide",
            file_name="sim.pdf",
            file_path="storage/key/sim.pdf",
            file_type="PDF",
            file_size_bytes=512,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        ver = DocumentVersion(
            id=ver_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=512,
            file_hash=doc.file_hash,
            file_path="storage/key/sim.pdf",
            created_by_id=user.id,
        )
        session.add_all([doc, ver])
        await session.commit()

    # Three orthogonal unit vectors
    v1 = [1.0] + [0.0] * 1535  # Perfectly aligned with e1
    v2 = [0.0, 1.0] + [0.0] * 1534  # Perfectly aligned with e2
    v3 = [0.0, 0.0, 1.0] + [0.0] * 1533  # Perfectly aligned with e3

    chunks = [
        DocumentChunkData(
            content="Primary chunk discussing vector math.",
            embedding=v1,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=0,
                token_count=5,
                char_count=35,
            ),
        ),
        DocumentChunkData(
            content="Secondary chunk discussing neural networks.",
            embedding=v2,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=1,
                token_count=5,
                char_count=42,
            ),
        ),
        DocumentChunkData(
            content="Tertiary chunk discussing database indexing.",
            embedding=v3,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=2,
                token_count=5,
                char_count=43,
            ),
        ),
    ]

    async with SessionLocal() as session:
        await VectorRepository.batch_insert_chunks(session=session, chunks=chunks)
        await session.commit()

    # Query vector close to v1: [0.99, 0.01, 0, ...]
    query_vec = [0.99, 0.01] + [0.0] * 1534

    async with SessionLocal() as session:
        results = await VectorRepository.search_vector_similarity(
            session=session,
            organization_id=org.id,
            query_embedding=query_vec,
            limit=2,
        )

        assert len(results) == 2
        # First result MUST be chunk 0 with high cosine similarity (~0.99)
        assert results[0].chunk_index == 0
        assert results[0].score > 0.95
        assert "vector math" in results[0].content

        # Second result is chunk 1 with low similarity
        assert results[1].chunk_index == 1
        assert results[1].score < 0.1

        # Test similarity threshold filtering: threshold 0.5 must exclude chunk 1
        filtered_results = await VectorRepository.search_vector_similarity(
            session=session,
            organization_id=org.id,
            query_embedding=query_vec,
            similarity_threshold=0.5,
            limit=10,
        )
        assert len(filtered_results) == 1
        assert filtered_results[0].chunk_index == 0


@pytest.mark.asyncio
async def test_multi_tenant_vector_isolation(setup_vector_records):
    """3. Test that queries scoped to Organization Alpha NEVER return Organization Beta chunks."""
    data = setup_vector_records
    org_a = data["org_a"]
    user_a = data["user_a"]
    org_b = data["org_b"]
    user_b = data["user_b"]

    doc_a_id = uuid.uuid4()
    ver_a_id = uuid.uuid4()
    doc_b_id = uuid.uuid4()
    ver_b_id = uuid.uuid4()

    async with SessionLocal() as session:
        doc_a = Document(
            id=doc_a_id,
            organization_id=org_a.id,
            uploaded_by_id=user_a.id,
            title="Alpha Financials",
            file_name="alpha.pdf",
            file_path="storage/key/alpha.pdf",
            file_type="PDF",
            file_size_bytes=100,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_a_id,
        )
        ver_a = DocumentVersion(
            id=ver_a_id,
            organization_id=org_a.id,
            document_id=doc_a_id,
            version_number=1,
            file_size_bytes=100,
            file_hash=doc_a.file_hash,
            file_path="storage/key/alpha.pdf",
            created_by_id=user_a.id,
        )
        doc_b = Document(
            id=doc_b_id,
            organization_id=org_b.id,
            uploaded_by_id=user_b.id,
            title="Beta Financials",
            file_name="beta.pdf",
            file_path="storage/key/beta.pdf",
            file_type="PDF",
            file_size_bytes=100,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_b_id,
        )
        ver_b = DocumentVersion(
            id=ver_b_id,
            organization_id=org_b.id,
            document_id=doc_b_id,
            version_number=1,
            file_size_bytes=100,
            file_hash=doc_b.file_hash,
            file_path="storage/key/beta.pdf",
            created_by_id=user_b.id,
        )
        session.add_all([doc_a, ver_a, doc_b, ver_b])
        await session.commit()

    # Both organizations store identical embedding vectors [1.0, 0, 0, ...]
    v = [1.0] + [0.0] * 1535

    chunks_a = [
        DocumentChunkData(
            content="Alpha confidential executive compensation.",
            embedding=v,
            metadata=ChunkMetadata(
                document_id=doc_a_id,
                version_id=ver_a_id,
                organization_id=org_a.id,
                chunk_index=0,
                token_count=5,
                char_count=40,
            ),
        )
    ]
    chunks_b = [
        DocumentChunkData(
            content="Beta confidential executive compensation.",
            embedding=v,
            metadata=ChunkMetadata(
                document_id=doc_b_id,
                version_id=ver_b_id,
                organization_id=org_b.id,
                chunk_index=0,
                token_count=5,
                char_count=39,
            ),
        )
    ]

    async with SessionLocal() as session:
        await VectorRepository.batch_insert_chunks(session=session, chunks=chunks_a)
        await VectorRepository.batch_insert_chunks(session=session, chunks=chunks_b)
        await session.commit()

    # Query as Organization Alpha
    async with SessionLocal() as session:
        results_a = await VectorRepository.search_vector_similarity(
            session=session,
            organization_id=org_a.id,
            query_embedding=v,
            limit=10,
        )
        # MUST only see Org Alpha's chunk
        assert len(results_a) == 1
        assert results_a[0].organization_id == org_a.id
        assert "Alpha confidential" in results_a[0].content
        assert results_a[0].document_id == doc_a_id

    # Query as Organization Beta
    async with SessionLocal() as session:
        results_b = await VectorRepository.search_vector_similarity(
            session=session,
            organization_id=org_b.id,
            query_embedding=v,
            limit=10,
        )
        # MUST only see Org Beta's chunk
        assert len(results_b) == 1
        assert results_b[0].organization_id == org_b.id
        assert "Beta confidential" in results_b[0].content
        assert results_b[0].document_id == doc_b_id


@pytest.mark.asyncio
async def test_active_version_filtering_and_supersession(setup_vector_records):
    """4. Test that deactivated older version chunks are excluded when active_only=True."""
    data = setup_vector_records
    org = data["org_a"]
    user = data["user_a"]

    doc_id = uuid.uuid4()
    ver_1_id = uuid.uuid4()
    ver_2_id = uuid.uuid4()

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=org.id,
            uploaded_by_id=user.id,
            title="Policy Manual",
            file_name="policy.pdf",
            file_path="storage/key/policy.pdf",
            file_type="PDF",
            file_size_bytes=200,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_1_id,
        )
        ver_1 = DocumentVersion(
            id=ver_1_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=200,
            file_hash=doc.file_hash,
            file_path="storage/key/policy_v1.pdf",
            is_active=False,  # Superseded
            created_by_id=user.id,
        )
        ver_2 = DocumentVersion(
            id=ver_2_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=2,
            file_size_bytes=220,
            file_hash=f"hash-{uuid.uuid4().hex}",
            file_path="storage/key/policy_v2.pdf",
            is_active=True,  # Active
            created_by_id=user.id,
        )
        session.add_all([doc, ver_1, ver_2])
        await session.commit()

    v = [1.0] + [0.0] * 1535

    # Insert v1 chunks as active originally
    v1_chunks = [
        DocumentChunkData(
            content="Outdated v1 vacation policy: 10 days per year.",
            embedding=v,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_1_id,
                organization_id=org.id,
                chunk_index=0,
                token_count=10,
                char_count=45,
            ),
        )
    ]
    # Insert v2 chunks
    v2_chunks = [
        DocumentChunkData(
            content="Current v2 vacation policy: 20 days per year.",
            embedding=v,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_2_id,
                organization_id=org.id,
                chunk_index=0,
                token_count=10,
                char_count=44,
            ),
        )
    ]

    async with SessionLocal() as session:
        await VectorRepository.batch_insert_chunks(session=session, chunks=v1_chunks)
        await VectorRepository.batch_insert_chunks(session=session, chunks=v2_chunks)
        # Deactivate v1 chunks
        deactivated_count = await VectorRepository.deactivate_chunks_by_version(
            session=session,
            organization_id=org.id,
            version_id=ver_1_id,
        )
        assert deactivated_count == 1
        await session.commit()

    # Query with active_only=True
    async with SessionLocal() as session:
        active_results = await VectorRepository.search_vector_similarity(
            session=session,
            organization_id=org.id,
            query_embedding=v,
            active_only=True,
        )
        assert len(active_results) == 1
        assert active_results[0].version_id == ver_2_id
        assert "Current v2 vacation policy" in active_results[0].content

        # Query with active_only=False -> both versions present
        all_results = await VectorRepository.search_vector_similarity(
            session=session,
            organization_id=org.id,
            query_embedding=v,
            active_only=False,
        )
        assert len(all_results) == 2


@pytest.mark.asyncio
async def test_full_text_search(setup_vector_records):
    """5. Test tsvector GIN full-text search against document chunks."""
    data = setup_vector_records
    org = data["org_a"]
    user = data["user_a"]

    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=org.id,
            uploaded_by_id=user.id,
            title="Tech Documentation",
            file_name="tech.txt",
            file_path="storage/key/tech.txt",
            file_type="TXT",
            file_size_bytes=300,
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        ver = DocumentVersion(
            id=ver_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=300,
            file_hash=doc.file_hash,
            file_path="storage/key/tech.txt",
            created_by_id=user.id,
        )
        session.add_all([doc, ver])
        await session.commit()

    v = [0.1] * 1536
    chunks = [
        DocumentChunkData(
            content="Kubernetes orchestrates containerized cloud applications across clusters.",
            embedding=v,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=0,
                token_count=10,
                char_count=65,
            ),
        ),
        DocumentChunkData(
            content="PostgreSQL pgvector provides high-performance HNSW index scans for embeddings.",
            embedding=v,
            metadata=ChunkMetadata(
                document_id=doc_id,
                version_id=ver_id,
                organization_id=org.id,
                chunk_index=1,
                token_count=10,
                char_count=75,
            ),
        ),
    ]

    async with SessionLocal() as session:
        await VectorRepository.batch_insert_chunks(session=session, chunks=chunks)
        await session.commit()

    async with SessionLocal() as session:
        # Search for "Kubernetes"
        k8s_results = await VectorRepository.search_full_text(
            session=session,
            organization_id=org.id,
            query_text="Kubernetes",
        )
        assert len(k8s_results) == 1
        assert k8s_results[0].chunk_index == 0
        assert "Kubernetes" in k8s_results[0].content
        assert k8s_results[0].score > 0

        # Search for "pgvector"
        pg_results = await VectorRepository.search_full_text(
            session=session,
            organization_id=org.id,
            query_text="pgvector",
        )
        assert len(pg_results) == 1
        assert pg_results[0].chunk_index == 1
        assert "pgvector" in pg_results[0].content


@pytest.mark.asyncio
async def test_end_to_end_pipeline_with_persistence(setup_vector_records):
    """6. Test end-to-end pipeline execution with persist_chunks=True transitions to COMPLETED."""
    data = setup_vector_records
    org = data["org_a"]
    user = data["user_a"]

    # Create temporary local storage
    temp_dir = tempfile.mkdtemp(prefix="rag_test_p8_storage_")
    storage = LocalStorageProvider(base_dir=temp_dir)

    # Simple sample text content
    content_bytes = (
        b"Enterprise RAG assistant architecture integrates PostgreSQL 16 and pgvector 0.8.0.\n\n"
        b"FastAPI powers the REST endpoints while Argon2id handles password hashing securely."
    )
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage_key = f"tenants/{org.id}/documents/{doc_id}/{ver_id}_sample.txt"

    async def _stream():
        yield content_bytes

    await storage.save(_stream(), storage_key, "text/plain")

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=org.id,
            uploaded_by_id=user.id,
            title="Architecture Summary",
            file_name="sample.txt",
            file_path=storage_key,
            file_type="TXT",
            file_size_bytes=len(content_bytes),
            file_hash=f"hash-{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        ver = DocumentVersion(
            id=ver_id,
            organization_id=org.id,
            document_id=doc_id,
            version_number=1,
            file_size_bytes=len(content_bytes),
            file_hash=doc.file_hash,
            file_path=storage_key,
            created_by_id=user.id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=org.id,
            document_id=doc_id,
            version_id=ver_id,
            idempotency_key=f"ingest_{doc_id}_{ver_id}",
            status="QUEUED",
            progress_percent=10,
        )
        session.add_all([doc, ver, job])
        await session.commit()

    pipeline = ChunkingAndEmbeddingPipeline(
        chunking_service=ChunkingService(chunk_size_tokens=50, chunk_overlap_tokens=10),
        embedding_service=EmbeddingService(api_key=None, dimensions=1536),
    )

    async with SessionLocal() as session:
        chunks, stats = await pipeline.execute_pipeline(
            session=session,
            document_id=doc_id,
            storage_provider=storage,
            persist_chunks=True,  # Triggers Phase 8 persistent storage!
        )

        assert len(chunks) >= 1
        assert stats.total_chunks == len(chunks)

    # Verify Document and Job state
    async with SessionLocal() as session:
        stmt = (
            select(Document)
            .options(selectinload(Document.ingestion_jobs))
            .where(Document.id == doc_id)
        )
        result = await session.execute(stmt)
        updated_doc = result.scalar_one()

        assert updated_doc.status == "COMPLETED"
        assert updated_doc.metadata_["chunk_count"] == len(chunks)

        job = updated_doc.ingestion_jobs[0]
        assert job.status == "COMPLETED"
        assert job.progress_percent == 100
        assert job.completed_at is not None

        # Verify chunks persisted in PostgreSQL
        stored_chunks = await VectorRepository.get_chunks_by_document(
            session=session,
            organization_id=org.id,
            document_id=doc_id,
        )
        assert len(stored_chunks) == len(chunks)
        assert stored_chunks[0].is_active is True
        assert stored_chunks[0].embedding is not None

    shutil.rmtree(temp_dir, ignore_errors=True)
