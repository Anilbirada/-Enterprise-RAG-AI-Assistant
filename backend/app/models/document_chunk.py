import uuid
from typing import TYPE_CHECKING, List, Optional
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_version import DocumentVersion
    from app.models.citation import MessageCitation


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Text chunk entity containing 1536d vector embedding and tsvector search target."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "chunk_index", name="uq_chunks_version_index"),
        UniqueConstraint("organization_id", "id", name="uq_chunks_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_chunks_org_document",
        ),
        ForeignKeyConstraint(
            ["organization_id", "version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_chunks_org_version",
        ),
        # Composite B-tree index for fast tenant-filtered document queries
        Index("idx_chunks_org_doc_version", "organization_id", "document_id", "version_id"),
        # Active version filtering index
        Index("idx_chunks_org_active", "organization_id", "is_active"),
        # GIN index for full-text search
        Index("idx_chunks_search_vector", "search_vector", postgresql_using="gin"),
        # HNSW Index for vector cosine similarity search with ef_construction and m parameters
        Index(
            "idx_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 1536-dimensional OpenAI text-embedding-3-small vector
    embedding: Mapped[Vector] = mapped_column(Vector(1536), nullable=False)

    # Generated full-text search vector stored in table
    search_vector: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=True,
    )

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="chunks",
        foreign_keys=[document_id],
    )
    version: Mapped["DocumentVersion"] = relationship(
        "DocumentVersion",
        back_populates="chunks",
        foreign_keys=[version_id],
    )
    citations: Mapped[List["MessageCitation"]] = relationship(
        "MessageCitation",
        back_populates="chunk",
        cascade="all, delete-orphan",
        foreign_keys="MessageCitation.chunk_id",
    )
