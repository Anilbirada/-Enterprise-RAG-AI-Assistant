from typing import TYPE_CHECKING, List
from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.user import User
    from app.models.document import Document
    from app.models.conversation import Conversation
    from app.models.ingestion_job import IngestionJob


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tenant boundary entity. All operational entities belong to an Organization."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    departments: Mapped[List["Department"]] = relationship(
        "Department", back_populates="organization", cascade="all, delete-orphan"
    )
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="organization", cascade="all, delete-orphan"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="organization", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="organization", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[List["IngestionJob"]] = relationship(
        "IngestionJob", back_populates="organization", cascade="all, delete-orphan"
    )
