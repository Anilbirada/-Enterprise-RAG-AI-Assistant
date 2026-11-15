import io
import shutil
import tempfile
import uuid
import docx
import pymupdf as fitz
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import NullPool

from app.core.exceptions import EntityNotFoundException
from app.core.security import get_password_hash
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.models.organization import Organization
from app.models.user import User
from app.services.chunking_embedding_pipeline import ChunkingAndEmbeddingPipeline
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.storage.local import LocalStorageProvider

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


def create_sample_pdf_with_sections() -> bytes:
    """Creates a 2-page sample PDF with headers and body text."""
    doc = fitz.open()
    p1 = doc.new_page(width=600, height=800)
    p1.insert_text(
        (50, 70),
        "Section 1: Enterprise RAG Overview\n\n"
        "Modern RAG systems combine dense semantic retrieval with sparse keyword search.\n"
        "By enforcing strict organization boundaries and token-aware chunking, systems achieve higher accuracy.\n"
        "PostgreSQL 16 with pgvector 0.8.0 provides native vector similarity matching."
    )
    p2 = doc.new_page(width=600, height=800)
    p2.insert_text(
        (50, 70),
        "Section 2: Security and Row-Level Security\n\n"
        "Multi-tenant isolation must be enforced via PostgreSQL Row-Level Security (RLS).\n"
        "Composite foreign keys guarantee that documents cannot be queried across tenant boundaries."
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_sample_docx_with_table() -> bytes:
    """Creates a sample DOCX with paragraphs and a Markdown-convertible table."""
    doc = docx.Document()
    doc.add_heading("Platform Specifications", level=1)
    doc.add_paragraph("Enterprise RAG architectural matrix:")

    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "Layer"
    table.cell(0, 1).text = "Technology"
    table.cell(1, 0).text = "Vector Storage"
    table.cell(1, 1).text = "pgvector 0.8.0"
    table.cell(2, 0).text = "Embedding Model"
    table.cell(2, 1).text = "text-embedding-3-small"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def temp_storage():
    """Provides isolated local storage directory for test execution."""
    temp_dir = tempfile.mkdtemp(prefix="rag_test_pipeline_storage_")
    storage = LocalStorageProvider(base_dir=temp_dir)
    yield storage, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def setup_pipeline_records():
    """Seeds test organization and user in PostgreSQL test database."""
    async with SessionLocal() as session:
        org = Organization(
            id=uuid.uuid4(),
            name="Pipeline Corp",
            slug=f"pipe-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=f"pipeline-admin-{uuid.uuid4().hex[:4]}@example.com",
            hashed_password=get_password_hash("Password123!"),
            full_name="Pipeline Admin",
            role="ORG_ADMIN",
            is_active=True,
        )
        session.add(user)
        await session.commit()

        return {"org": org, "user": user}


@pytest.mark.asyncio
async def test_chunking_embedding_pipeline_pdf(setup_pipeline_records, temp_storage):
    """Test full pipeline execution on a PDF document: extraction -> chunking -> embedding."""
    data = setup_pipeline_records
    storage, _ = temp_storage

    pdf_bytes = create_sample_pdf_with_sections()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage_key = f"tenants/{data['org'].id}/documents/{doc_id}/{ver_id}_architecture.pdf"

    async def _stream():
        yield pdf_bytes

    await storage.save(_stream(), storage_key, "application/pdf")

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=data["org"].id,
            uploaded_by_id=data["user"].id,
            title="Enterprise Architecture Overview",
            file_name="architecture_overview.pdf",
            file_path=storage_key,
            file_type="PDF",
            file_size_bytes=len(pdf_bytes),
            file_hash=f"sha256_mock_hash_{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=data["org"].id,
            document_id=doc_id,
            version_id=ver_id,
            idempotency_key=f"ingest_{doc_id}_{ver_id}",
            status="QUEUED",
            progress_percent=10,
        )
        session.add_all([doc, job])
        await session.commit()

    # Instantiate pipeline with deterministic mock embeddings
    pipeline = ChunkingAndEmbeddingPipeline(
        chunking_service=ChunkingService(chunk_size_tokens=100, chunk_overlap_tokens=20),
        embedding_service=EmbeddingService(api_key=None, dimensions=1536),
    )

    async with SessionLocal() as session:
        chunks, stats = await pipeline.execute_pipeline(
            session=session,
            document_id=doc_id,
            storage_provider=storage,
        )

        assert len(chunks) >= 2
        assert stats.total_chunks == len(chunks)
        assert stats.total_tokens > 20
        assert stats.average_tokens_per_chunk > 0

        # Verify each chunk has valid 1536-dimensional embeddings
        for i, chunk in enumerate(chunks):
            assert chunk.metadata.chunk_index == i
            assert chunk.metadata.organization_id == data["org"].id
            assert chunk.metadata.document_id == doc_id
            assert chunk.metadata.version_id == ver_id
            assert chunk.metadata.token_count <= 100
            assert chunk.metadata.char_count > 0
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536

    # Verify Document and Job database state
    async with SessionLocal() as session:
        stmt = (
            select(Document)
            .options(selectinload(Document.ingestion_jobs))
            .where(Document.id == doc_id)
        )
        result = await session.execute(stmt)
        updated_doc = result.scalar_one()

        assert updated_doc.status == "EMBEDDING"
        assert updated_doc.metadata_["chunk_count"] == len(chunks)
        assert updated_doc.metadata_["embedding_dimension"] == 1536
        assert updated_doc.metadata_["embedding_model"] == "text-embedding-3-small"

        job = updated_doc.ingestion_jobs[0]
        assert job.progress_percent == 75


@pytest.mark.asyncio
async def test_chunking_embedding_pipeline_docx_tables(setup_pipeline_records, temp_storage):
    """Test pipeline chunking on a DOCX with tables, verifying table detection."""
    data = setup_pipeline_records
    storage, _ = temp_storage

    docx_bytes = create_sample_docx_with_table()
    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage_key = f"tenants/{data['org'].id}/documents/{doc_id}/{ver_id}_specs.docx"

    async def _stream():
        yield docx_bytes

    await storage.save(_stream(), storage_key, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=data["org"].id,
            uploaded_by_id=data["user"].id,
            title="Specs",
            file_name="specs.docx",
            file_path=storage_key,
            file_type="DOCX",
            file_size_bytes=len(docx_bytes),
            file_hash=f"sha256_mock_hash_{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=data["org"].id,
            document_id=doc_id,
            version_id=ver_id,
            idempotency_key=f"ingest_{doc_id}_{ver_id}",
            status="QUEUED",
            progress_percent=10,
        )
        session.add_all([doc, job])
        await session.commit()

    pipeline = ChunkingAndEmbeddingPipeline(
        chunking_service=ChunkingService(chunk_size_tokens=150, chunk_overlap_tokens=20),
        embedding_service=EmbeddingService(api_key=None, dimensions=1536),
    )

    async with SessionLocal() as session:
        chunks, stats = await pipeline.execute_pipeline(
            session=session,
            document_id=doc_id,
            storage_provider=storage,
        )

        assert len(chunks) >= 1
        assert stats.chunks_with_tables >= 1
        has_table_pipe = any("|" in c.content for c in chunks)
        assert has_table_pipe is True


@pytest.mark.asyncio
async def test_chunking_embedding_pipeline_not_found(temp_storage):
    """Test pipeline raises EntityNotFoundException for non-existent document."""
    storage, _ = temp_storage
    pipeline = ChunkingAndEmbeddingPipeline()

    async with SessionLocal() as session:
        with pytest.raises(EntityNotFoundException):
            await pipeline.execute_pipeline(
                session=session,
                document_id=uuid.uuid4(),
                storage_provider=storage,
            )


@pytest.mark.asyncio
async def test_chunking_embedding_pipeline_failure_handling(setup_pipeline_records, temp_storage):
    """Test pipeline properly transitions document and job to FAILED when an exception occurs."""
    data = setup_pipeline_records
    storage, _ = temp_storage

    doc_id = uuid.uuid4()
    ver_id = uuid.uuid4()
    job_id = uuid.uuid4()

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=data["org"].id,
            uploaded_by_id=data["user"].id,
            title="Faulty Document",
            file_name="faulty.txt",
            file_path="non_existent/path/faulty.txt",
            file_type="TXT",
            file_size_bytes=100,
            file_hash=f"sha256_mock_hash_{uuid.uuid4().hex}",
            status="UPLOADED",
            current_version_id=ver_id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=data["org"].id,
            document_id=doc_id,
            version_id=ver_id,
            idempotency_key=f"ingest_{doc_id}_{ver_id}",
            status="QUEUED",
            progress_percent=10,
        )
        session.add_all([doc, job])
        await session.commit()

    pipeline = ChunkingAndEmbeddingPipeline()

    async with SessionLocal() as session:
        with pytest.raises(Exception):
            await pipeline.execute_pipeline(
                session=session,
                document_id=doc_id,
                storage_provider=storage,
            )

    # Verify status transitioned to FAILED
    async with SessionLocal() as session:
        stmt = (
            select(Document)
            .options(selectinload(Document.ingestion_jobs))
            .where(Document.id == doc_id)
        )
        result = await session.execute(stmt)
        doc = result.scalar_one()

        assert doc.status == "FAILED"
        assert doc.error_message is not None
        assert doc.ingestion_jobs[0].status == "FAILED"
