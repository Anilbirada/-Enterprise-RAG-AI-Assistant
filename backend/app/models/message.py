import uuid
from typing import TYPE_CHECKING, List
from sqlalchemy import Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.citation import MessageCitation
    from app.models.feedback import Feedback


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Individual prompt or response message within a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_messages_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_messages_org_conversation",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # USER, ASSISTANT, SYSTEM
    content: Mapped[str] = mapped_column(Text, nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_parameters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
        foreign_keys=[conversation_id],
    )
    citations: Mapped[List["MessageCitation"]] = relationship(
        "MessageCitation",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageCitation.rank_position",
        foreign_keys="MessageCitation.message_id",
    )
    feedback: Mapped[List["Feedback"]] = relationship(
        "Feedback",
        back_populates="message",
        cascade="all, delete-orphan",
        foreign_keys="Feedback.message_id",
    )
