import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.department import Department
    from app.models.user import User
    from app.models.document_version import DocumentVersion
    from app.models.document_chunk import DocumentChunk
    from app.models.ingestion_job import IngestionJob


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Document entity tracking uploaded knowledge assets and current active state."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_documents_org_id"),
        UniqueConstraint("organization_id", "file_hash", name="uq_documents_org_file_hash"),
        CheckConstraint("file_size_bytes > 0", name="chk_documents_size_positive"),
        CheckConstraint(
            "file_type IN ('PDF', 'DOCX', 'TXT')",
            name="chk_documents_file_type",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'UPLOADED', 'PARSING', 'CHUNKING', 'EMBEDDING', 'COMPLETED', 'FAILED')",
            name="chk_documents_status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Active version pointer
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="documents")
    department: Mapped[Optional["Department"]] = relationship("Department", back_populates="documents")
    uploader: Mapped["User"] = relationship("User", back_populates="uploaded_documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentVersion.document_id",
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentChunk.document_id",
    )
    ingestion_jobs: Mapped[List["IngestionJob"]] = relationship(
        "IngestionJob",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="IngestionJob.document_id",
    )
