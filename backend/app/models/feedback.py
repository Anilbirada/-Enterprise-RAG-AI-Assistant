import uuid
from typing import TYPE_CHECKING, Optional
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


class Feedback(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User evaluation (thumbs up/down and comments) for AI-generated answers."""

    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_user_message_feedback"),
        UniqueConstraint("organization_id", "id", name="uq_feedback_org_id"),
        CheckConstraint("rating IN (1, -1)", name="chk_feedback_rating_values"),
        ForeignKeyConstraint(
            ["organization_id", "message_id"],
            ["messages.organization_id", "messages.id"],
            ondelete="CASCADE",
            name="fk_feedback_org_message",
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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1 for thumbs up, -1 for thumbs down
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    # Relationships
    message: Mapped["Message"] = relationship("Message", back_populates="feedback", foreign_keys=[message_id])
    user: Mapped["User"] = relationship("User", back_populates="feedback_submissions")
