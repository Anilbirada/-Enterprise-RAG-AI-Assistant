import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Default table name is snake_cased pluralized class name."""
        return cls.__name__.lower() + "s"

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model instance into a dictionary."""
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


class UUIDPrimaryKeyMixin:
    """Mixin providing standard UUID v4 primary keys."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,
    )


class TimestampMixin:
    """Mixin providing created_at and updated_at with UTC timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
