import io
import logging
import uuid
from pathlib import Path
from typing import List, Optional, Tuple
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import ConflictException, EntityNotFoundException, ValidationException
from app.models.department import Department
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.models.user import User
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
    DocumentVersionResponse,
    IngestionJobSummaryResponse,
)
from app.services.antivirus_service import AntivirusScanner
from app.services.document_validation_service import (
    create_bounded_upload_stream,
    inspect_magic_signature,
    sanitize_filename,
    validate_file_extension,
    verify_docx_package,
)
from app.services.storage.base import StorageProvider

logger = logging.getLogger("enterprise_rag.document_service")


class DocumentService:
    """Service orchestrating document upload, validation, deduplication, storage, and lifecycle."""

    @staticmethod
    async def upload_document(
        session: AsyncSession,
        current_user: User,
        upload_file: UploadFile,
        storage_provider: StorageProvider,
        antivirus_scanner: AntivirusScanner,
        title: Optional[str] = None,
        department_id: Optional[uuid.UUID] = None,
    ) -> DocumentUploadResponse:
        """Handles staged document upload, cryptographic deduplication, and atomic DB registration."""
        settings = get_settings()

        # 1. Extension & filename sanitation
        ext = validate_file_extension(upload_file.filename or "")
        safe_filename = sanitize_filename(upload_file.filename or "")
        doc_title = title.strip() if title and title.strip() else Path(safe_filename).stem

        # 2. Verify Department ownership if supplied
        if department_id:
            dept_stmt = select(Department).where(
                Department.id == department_id,
                Department.organization_id == current_user.organization_id,
            )
            dept_res = await session.execute(dept_stmt)
            if not dept_res.scalar_one_or_none():
                raise ValidationException(
                    f"Department '{department_id}' does not exist or does not belong to your organization."
                )

        # 3. Inspect magic bytes and initialize size-bounded streaming
        stream, header_chunk = await create_bounded_upload_stream(
            upload_file=upload_file,
            max_size_bytes=settings.MAX_UPLOAD_FILE_SIZE_BYTES,
        )
        file_type, content_type = inspect_magic_signature(header_chunk, ext)

        # 4. Generate server-side UUID identifiers
        doc_id = uuid.uuid4()
        version_id = uuid.uuid4()
        job_id = uuid.uuid4()
        storage_key = f"tenants/{current_user.organization_id}/documents/{doc_id}/{version_id}_{safe_filename}"

        # 5. Stage write to storage engine
        try:
            storage_meta = await storage_provider.save(
                stream=stream,
                storage_key=storage_key,
                content_type=content_type,
            )
        except Exception as exc:
            logger.error(f"Failed writing upload stream to storage: {exc}")
            raise

        # 6. Deep inspection & antivirus validation on staged file
        try:
            if ext == ".docx":
                # Deep inspect DOCX OpenXML structure
                chunks = []
                async for chunk in storage_provider.get(storage_key):
                    chunks.append(chunk)
                verify_docx_package(b"".join(chunks))

            # Optional antivirus scan hook
            is_clean = await antivirus_scanner.scan_file(storage_key)
            if not is_clean:
                raise ValidationException("Malware or security threat detected in uploaded document.")

        except Exception:
            # Compensating cleanup of staged file on validation failure
            await storage_provider.delete(storage_key)
            raise

        # 7. Organization-level Duplicate Hash Detection
        file_hash = storage_meta.checksum_sha256
        dup_stmt = select(Document).where(
            Document.organization_id == current_user.organization_id,
            Document.file_hash == file_hash,
        )
        dup_res = await session.execute(dup_stmt)
        existing_doc = dup_res.scalar_one_or_none()

        if existing_doc:
            # Compensating cleanup: delete newly staged duplicate file
            await storage_provider.delete(storage_key)
            logger.info(
                f"Duplicate file upload rejected for tenant {current_user.organization_id}: "
                f"hash {file_hash} matches existing doc '{existing_doc.id}'"
            )
            raise ConflictException(
                f"A document with an identical cryptographic fingerprint (SHA-256: {file_hash}) "
                f"already exists in this organization with ID '{existing_doc.id}' (Title: '{existing_doc.title}').",
                details={
                    "existing_document_id": str(existing_doc.id),
                    "existing_title": existing_doc.title,
                    "file_hash": file_hash,
                },
            )

        # 8. Atomic Database Transaction
        try:
            # Create Document entity
            doc = Document(
                id=doc_id,
                organization_id=current_user.organization_id,
                department_id=department_id,
                uploaded_by_id=current_user.id,
                title=doc_title,
                file_name=safe_filename,
                file_path=storage_key,  # Store opaque storage key, never expose physical filesystem path
                file_type=file_type,
                file_hash=file_hash,
                file_size_bytes=storage_meta.file_size_bytes,
                status="UPLOADED",
                current_version_id=version_id,
                metadata_={
                    "original_filename": upload_file.filename,
                    "content_type": content_type,
                    "storage_provider": settings.STORAGE_PROVIDER,
                },
            )

            # Create initial DocumentVersion (v1)
            version = DocumentVersion(
                id=version_id,
                organization_id=current_user.organization_id,
                document_id=doc_id,
                version_number=1,
                file_path=storage_key,
                file_hash=file_hash,
                file_size_bytes=storage_meta.file_size_bytes,
                is_active=True,
                created_by_id=current_user.id,
                change_summary="Initial document upload",
                metadata_={"content_type": content_type},
            )

            # Create IngestionJob record (QUEUED)
            job = IngestionJob(
                id=job_id,
                organization_id=current_user.organization_id,
                document_id=doc_id,
                version_id=version_id,
                idempotency_key=f"ingest_{doc_id}_{version_id}",
                status="QUEUED",
            )

            session.add_all([doc, version, job])
            await session.flush()
            await session.commit()

            logger.info(
                f"Document '{doc_title}' ({doc_id}) successfully uploaded and registered for tenant {current_user.organization_id}"
            )
            return DocumentUploadResponse(
                document_id=doc_id,
                version_id=version_id,
                job_id=job_id,
                organization_id=current_user.organization_id,
                department_id=department_id,
                title=doc_title,
                file_name=safe_filename,
                file_type=file_type,
                file_size_bytes=storage_meta.file_size_bytes,
                file_hash=file_hash,
                status=doc.status,
                created_at=doc.created_at,
            )

        except IntegrityError as exc:
            # Handle concurrent duplicate upload race condition
            await session.rollback()
            await storage_provider.delete(storage_key)
            if "uq_documents_org_file_hash" in str(exc):
                logger.warning(f"Concurrent duplicate upload race detected for hash {file_hash}")
                raise ConflictException(
                    f"A document with identical SHA-256 hash '{file_hash}' was just registered by another request."
                )
            logger.error(f"Database IntegrityError during document upload: {exc}")
            raise
        except Exception as exc:
            await session.rollback()
            # Compensating cleanup on DB failure
            await storage_provider.delete(storage_key)
            logger.error(f"Database transaction failed during document upload: {exc}")
            raise

    @staticmethod
    async def list_documents(
        session: AsyncSession,
        organization_id: uuid.UUID,
        department_id: Optional[uuid.UUID] = None,
        status_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> DocumentListResponse:
        """Lists documents belonging to the authenticated tenant with pagination."""
        base_query = select(Document).where(Document.organization_id == organization_id)

        if department_id:
            base_query = base_query.where(Document.department_id == department_id)
        if status_filter:
            base_query = base_query.where(Document.status == status_filter.upper())

        # Count total
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_count = (await session.execute(count_stmt)).scalar() or 0

        # Query items ordered by newest first
        stmt = base_query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
        result = await session.execute(stmt)
        docs = result.scalars().all()

        return DocumentListResponse(
            items=[DocumentResponse.model_validate(doc) for doc in docs],
            total=total_count,
            skip=skip,
            limit=limit,
        )

    @staticmethod
    async def get_document(
        session: AsyncSession,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DocumentDetailResponse:
        """Fetches full document details including versions and latest ingestion job."""
        stmt = (
            select(Document)
            .options(
                selectinload(Document.versions),
                selectinload(Document.ingestion_jobs),
            )
            .where(
                Document.id == document_id,
                Document.organization_id == organization_id,
            )
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise EntityNotFoundException("Document", document_id)

        # Sort versions by version_number ascending
        sorted_versions = sorted(doc.versions, key=lambda v: v.version_number)
        
        # Latest job
        latest_job = None
        if doc.ingestion_jobs:
            latest_job_record = sorted(doc.ingestion_jobs, key=lambda j: j.created_at, reverse=True)[0]
            latest_job = IngestionJobSummaryResponse.model_validate(latest_job_record)

        return DocumentDetailResponse(
            id=doc.id,
            organization_id=doc.organization_id,
            department_id=doc.department_id,
            uploaded_by_id=doc.uploaded_by_id,
            title=doc.title,
            file_name=doc.file_name,
            file_type=doc.file_type,
            file_size_bytes=doc.file_size_bytes,
            file_hash=doc.file_hash,
            status=doc.status,
            error_message=doc.error_message,
            current_version_id=doc.current_version_id,
            metadata_=doc.metadata_,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            versions=[DocumentVersionResponse.model_validate(v) for v in sorted_versions],
            latest_job=latest_job,
        )

    @staticmethod
    async def get_document_status(
        session: AsyncSession,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> DocumentStatusResponse:
        """Lightweight status query for document ingestion polling."""
        stmt = (
            select(Document)
            .options(selectinload(Document.ingestion_jobs))
            .where(
                Document.id == document_id,
                Document.organization_id == organization_id,
            )
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise EntityNotFoundException("Document", document_id)

        job_id = None
        job_status = None
        if doc.ingestion_jobs:
            latest_job = sorted(doc.ingestion_jobs, key=lambda j: j.created_at, reverse=True)[0]
            job_id = latest_job.id
            job_status = latest_job.status

        return DocumentStatusResponse(
            document_id=doc.id,
            title=doc.title,
            document_status=doc.status,
            current_version_id=doc.current_version_id,
            job_id=job_id,
            job_status=job_status,
            error_message=doc.error_message,
            updated_at=doc.updated_at,
        )

    @staticmethod
    async def delete_document(
        session: AsyncSession,
        organization_id: uuid.UUID,
        document_id: uuid.UUID,
        storage_provider: StorageProvider,
    ) -> DocumentDeleteResponse:
        """Deletes a document from the database (cascading) and removes all physical stored versions."""
        stmt = (
            select(Document)
            .options(selectinload(Document.versions))
            .where(
                Document.id == document_id,
                Document.organization_id == organization_id,
            )
        )
        result = await session.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise EntityNotFoundException("Document", document_id)

        # Collect storage keys for all versions
        storage_keys = [doc.file_path]
        for v in doc.versions:
            if v.file_path not in storage_keys:
                storage_keys.append(v.file_path)

        # Delete from DB
        await session.delete(doc)
        await session.commit()

        # Delete stored files
        for key in storage_keys:
            try:
                await storage_provider.delete(key)
            except Exception as exc:
                logger.warning(f"Non-fatal error deleting storage key '{key}': {exc}")

        logger.info(f"Deleted document '{document_id}' and {len(storage_keys)} physical version(s).")
        return DocumentDeleteResponse(
            success=True,
            message="Document and all associated versions deleted successfully.",
            document_id=document_id,
        )
