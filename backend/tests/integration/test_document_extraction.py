import io
import shutil
import tempfile
import uuid
import docx
import pymupdf as fitz
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import get_password_hash
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.organization import Organization
from app.models.user import User
from app.services.document_extraction_service import DocumentExtractionService
from app.services.storage.local import LocalStorageProvider

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/enterprise_rag_test_db"
engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


def create_sample_pdf_with_text() -> bytes:
    """Creates a 2-page PDF with text and section headers using PyMuPDF."""
    doc = fitz.open()
    p1 = doc.new_page(width=600, height=800)
    p1.insert_text((50, 70), "Chapter 1: Enterprise RAG Architecture\nRetrieval mechanisms and PostgreSQL pgvector integration.")
    p2 = doc.new_page(width=600, height=800)
    p2.insert_text((50, 70), "Chapter 2: Vector Similarity Search\nHNSW indexing benchmarks and tenant isolation.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_sample_docx_with_table() -> bytes:
    """Creates a structured DOCX with headings and a table."""
    doc = docx.Document()
    doc.add_heading("Internal Engineering Standards", level=1)
    doc.add_paragraph("Mandatory guidelines for production services.")
    doc.add_heading("Database Tier", level=2)
    doc.add_paragraph("PostgreSQL 16 with pgvector 0.8.0", style="List Bullet")
    
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Component"
    table.cell(0, 1).text = "Technology"
    table.cell(1, 0).text = "Vector Store"
    table.cell(1, 1).text = "pgvector"
    
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def temp_extraction_storage():
    """Provides isolated local storage for extraction integration testing."""
    temp_dir = tempfile.mkdtemp(prefix="rag_test_extraction_storage_")
    storage = LocalStorageProvider(base_dir=temp_dir)
    yield storage, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def setup_extraction_records():
    """Seeds test organization and user in PostgreSQL."""
    async with SessionLocal() as session:
        org = Organization(
            id=uuid.uuid4(),
            name="Extraction Corp",
            slug=f"extract-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(org)
        await session.flush()

        user = User(
            id=uuid.uuid4(),
            organization_id=org.id,
            email=f"author-{uuid.uuid4().hex[:6]}@extract.com",
            hashed_password=get_password_hash("Password123!"),
            full_name="Doc Author",
            role="KNOWLEDGE_MANAGER",
            is_active=True,
        )
        session.add(user)
        await session.commit()

        return {"org": org, "user": user}


@pytest.mark.asyncio
async def test_end_to_end_pdf_extraction(
    setup_extraction_records,
    temp_extraction_storage,
):
    """Test full extraction lifecycle for PDF: storage reading, parsing, and metadata updating."""
    data = setup_extraction_records
    storage, _ = temp_extraction_storage
    pdf_bytes = create_sample_pdf_with_text()

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage_key = f"tenants/{data['org'].id}/documents/{doc_id}/{version_id}_sample.pdf"

    # 1. Save to storage
    async def _stream():
        yield pdf_bytes

    await storage.save(_stream(), storage_key, "application/pdf")

    # 2. Create DB records in UPLOADED state
    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=data["org"].id,
            uploaded_by_id=data["user"].id,
            title="Architecture Guide",
            file_name="sample.pdf",
            file_path=storage_key,
            file_type="PDF",
            file_hash="dummy_pdf_hash",
            file_size_bytes=len(pdf_bytes),
            status="UPLOADED",
            current_version_id=version_id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=data["org"].id,
            document_id=doc_id,
            version_id=version_id,
            idempotency_key=f"ingest_{doc_id}_{version_id}",
            status="QUEUED",
        )
        session.add_all([doc, job])
        await session.commit()

    # 3. Process extraction
    async with SessionLocal() as session:
        extracted = await DocumentExtractionService.process_document_extraction(
            session=session,
            document_id=doc_id,
            storage_provider=storage,
        )

    # 4. Verify extraction output
    assert extracted.file_type == "PDF"
    assert extracted.total_pages == 2
    assert "Chapter 1: Enterprise RAG Architecture" in extracted.full_text
    assert "Chapter 2: Vector Similarity Search" in extracted.full_text

    # 5. Verify database updates
    async with SessionLocal() as session:
        doc_updated = await session.get(Document, doc_id)
        assert doc_updated.status == "PARSING"
        assert doc_updated.metadata_["page_count"] == 2
        assert doc_updated.metadata_["word_count"] > 10
        assert doc_updated.error_message is None

        job_updated = await session.get(IngestionJob, job_id)
        assert job_updated.status == "PARSING"
        assert job_updated.progress_percent == 25


@pytest.mark.asyncio
async def test_end_to_end_docx_extraction(
    setup_extraction_records,
    temp_extraction_storage,
):
    """Test full extraction lifecycle for DOCX: headings, bullet points, and tables."""
    data = setup_extraction_records
    storage, _ = temp_extraction_storage
    docx_bytes = create_sample_docx_with_table()

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage_key = f"tenants/{data['org'].id}/documents/{doc_id}/{version_id}_standards.docx"

    async def _stream():
        yield docx_bytes

    await storage.save(_stream(), storage_key, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=data["org"].id,
            uploaded_by_id=data["user"].id,
            title="Engineering Standards",
            file_name="standards.docx",
            file_path=storage_key,
            file_type="DOCX",
            file_hash="dummy_docx_hash",
            file_size_bytes=len(docx_bytes),
            status="UPLOADED",
            current_version_id=version_id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=data["org"].id,
            document_id=doc_id,
            version_id=version_id,
            idempotency_key=f"ingest_{doc_id}_{version_id}",
            status="QUEUED",
        )
        session.add_all([doc, job])
        await session.commit()

    async with SessionLocal() as session:
        extracted = await DocumentExtractionService.process_document_extraction(
            session=session,
            document_id=doc_id,
            storage_provider=storage,
        )

    assert extracted.file_type == "DOCX"
    assert "# Internal Engineering Standards" in extracted.full_text
    assert "- PostgreSQL 16 with pgvector 0.8.0" in extracted.full_text
    assert "| Component | Technology |" in extracted.full_text
    assert extracted.total_tables == 1

    async with SessionLocal() as session:
        doc_updated = await session.get(Document, doc_id)
        assert doc_updated.status == "PARSING"
        assert doc_updated.metadata_["table_count"] == 1


@pytest.mark.asyncio
async def test_extraction_failure_lifecycle(
    setup_extraction_records,
    temp_extraction_storage,
):
    """Test extraction failure on corrupted file transitions document and job to FAILED."""
    data = setup_extraction_records
    storage, _ = temp_extraction_storage
    corrupted_pdf_bytes = b"%PDF-1.7 Corrupted unparseable bytes"

    doc_id = uuid.uuid4()
    version_id = uuid.uuid4()
    job_id = uuid.uuid4()
    storage_key = f"tenants/{data['org'].id}/documents/{doc_id}/{version_id}_corrupt.pdf"

    async def _stream():
        yield corrupted_pdf_bytes

    await storage.save(_stream(), storage_key, "application/pdf")

    async with SessionLocal() as session:
        doc = Document(
            id=doc_id,
            organization_id=data["org"].id,
            uploaded_by_id=data["user"].id,
            title="Corrupted Document",
            file_name="corrupt.pdf",
            file_path=storage_key,
            file_type="PDF",
            file_hash="dummy_corrupt_hash",
            file_size_bytes=len(corrupted_pdf_bytes),
            status="UPLOADED",
            current_version_id=version_id,
        )
        job = IngestionJob(
            id=job_id,
            organization_id=data["org"].id,
            document_id=doc_id,
            version_id=version_id,
            idempotency_key=f"ingest_{doc_id}_{version_id}",
            status="QUEUED",
        )
        session.add_all([doc, job])
        await session.commit()

    # Process extraction expecting failure
    async with SessionLocal() as session:
        with pytest.raises(Exception):
            await DocumentExtractionService.process_document_extraction(
                session=session,
                document_id=doc_id,
                storage_provider=storage,
            )

    # Verify status transitioned to FAILED and error message was recorded
    async with SessionLocal() as session:
        doc_failed = await session.get(Document, doc_id)
        assert doc_failed.status == "FAILED"
        assert doc_failed.error_message is not None
        assert "Corrupted or invalid PDF" in doc_failed.error_message

        job_failed = await session.get(IngestionJob, job_id)
        assert job_failed.status == "FAILED"
        assert job_failed.error_message is not None
