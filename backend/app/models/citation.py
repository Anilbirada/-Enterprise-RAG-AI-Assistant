import uuid
from typing import TYPE_CHECKING
from sqlalchemy import Float, ForeignKey, ForeignKeyConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.document_chunk import DocumentChunk


class MessageCitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Verifiable source grounding link connecting an AI message to a specific retrieved chunk."""

    __tablename__ = "message_citations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_citations_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "message_id"],
            ["messages.organization_id", "messages.id"],
            ondelete="CASCADE",
            name="fk_citations_org_message",
        ),
        ForeignKeyConstraint(
            ["organization_id", "chunk_id"],
            ["document_chunks.organization_id", "document_chunks.id"],
            ondelete="CASCADE",
            name="fk_citations_org_chunk",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="citations", foreign_keys=[message_id])
    chunk: Mapped["DocumentChunk"] = relationship("DocumentChunk", back_populates="citations", foreign_keys=[chunk_id])
