import uuid
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db, require_permissions
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.antivirus_service import AntivirusScanner, get_antivirus_scanner
from app.services.document_service import DocumentService
from app.services.storage.base import StorageProvider
from app.services.storage import get_storage_provider

router = APIRouter(prefix="/documents", tags=["Documents"])


async def _run_document_ingestion_task(document_id: uuid.UUID) -> None:
    """Executes layout extraction, chunking, embedding, and vector storage in background."""
    from app.database.session import AsyncSessionLocal
    from app.services.chunking_embedding_pipeline import ChunkingAndEmbeddingPipeline
    import logging

    log = logging.getLogger("enterprise_rag.ingestion_task")
    log.info(f"Triggering background ingestion for document '{document_id}'")
    try:
        async with AsyncSessionLocal() as session:
            storage = get_storage_provider()
            pipeline = ChunkingAndEmbeddingPipeline()
            chunks, stats = await pipeline.execute_pipeline(
                session=session,
                document_id=document_id,
                storage_provider=storage,
                persist_chunks=True,
            )
            log.info(f"Ingestion completed for document '{document_id}': {len(chunks)} chunks stored.")
    except Exception as e:
        log.error(f"Background ingestion pipeline failed for document '{document_id}': {e}", exc_info=True)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload knowledge base document (PDF, DOCX, TXT)",
    description=(
        "Securely uploads, inspects, and stages an enterprise document. "
        "Calculates cryptographic SHA-256 fingerprints for organization-level deduplication, "
        "and queues an atomic background ingestion job."
    ),
    dependencies=[Depends(require_permissions(Permission.UPLOAD_DOCUMENTS))],
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Document file to upload (PDF, DOCX, TXT)"),
    title: Optional[str] = Form(None, description="Optional human-readable title for the document"),
    department_id: Optional[uuid.UUID] = Form(None, description="Optional department UUID ownership"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
    storage_provider: StorageProvider = Depends(get_storage_provider),
    antivirus_scanner: AntivirusScanner = Depends(get_antivirus_scanner),
) -> DocumentUploadResponse:
    """Endpoint for uploading documents with strict validation and organization scoping."""
    result = await DocumentService.upload_document(
        session=session,
        current_user=current_user,
        upload_file=file,
        storage_provider=storage_provider,
        antivirus_scanner=antivirus_scanner,
        title=title,
        department_id=department_id,
    )
    background_tasks.add_task(_run_document_ingestion_task, result.document_id)
    return result


@router.post(
    "/{document_id}/ingest",
    summary="Trigger document ingestion",
    description="Manually triggers extraction, chunking, and vector embedding for a document.",
    dependencies=[Depends(require_permissions(Permission.UPLOAD_DOCUMENTS))],
)
async def trigger_document_ingestion(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
):
    await DocumentService.get_document_detail(session, document_id, current_user.organization_id)
    background_tasks.add_task(_run_document_ingestion_task, document_id)
    return {"status": "QUEUED", "message": f"Ingestion triggered for document '{document_id}'"}


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List tenant documents",
    description="Lists documents belonging to the authenticated user's organization with optional filtering.",
    dependencies=[Depends(require_permissions(Permission.VIEW_DOCUMENTS))],
)
async def list_documents(
    department_id: Optional[uuid.UUID] = Query(None, description="Filter documents by department UUID"),
    status: Optional[str] = Query(None, description="Filter documents by lifecycle status (UPLOADED, COMPLETED, etc.)"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=100, description="Pagination batch limit"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """Retrieves paginated document collection within tenant boundary."""
    return await DocumentService.list_documents(
        session=session,
        organization_id=current_user.organization_id,
        department_id=department_id,
        status_filter=status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document details",
    description="Retrieves comprehensive document metadata including historical versions and latest ingestion job.",
    dependencies=[Depends(require_permissions(Permission.VIEW_DOCUMENTS))],
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentDetailResponse:
    """Fetches single document details by ID."""
    return await DocumentService.get_document(
        session=session,
        organization_id=current_user.organization_id,
        document_id=document_id,
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Poll document ingestion status",
    description="Lightweight status endpoint for polling processing and ingestion job progress.",
    dependencies=[Depends(require_permissions(Permission.VIEW_DOCUMENTS))],
)
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentStatusResponse:
    """Polls processing status for a given document."""
    return await DocumentService.get_document_status(
        session=session,
        organization_id=current_user.organization_id,
        document_id=document_id,
    )


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete document and stored files",
    description="Permanently deletes document, its versions, and associated physical files from storage.",
    dependencies=[Depends(require_permissions(Permission.MANAGE_DOCUMENTS))],
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
    storage_provider: StorageProvider = Depends(get_storage_provider),
) -> DocumentDeleteResponse:
    """Deletes document and cascades storage file cleanup."""
    return await DocumentService.delete_document(
        session=session,
        organization_id=current_user.organization_id,
        document_id=document_id,
        storage_provider=storage_provider,
    )
