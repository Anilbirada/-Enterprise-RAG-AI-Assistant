import uuid
from typing import TYPE_CHECKING, List
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User
    from app.models.document import Document


class Department(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Sub-tenant organizational unit used for granular document authorization."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_departments_org_code"),
        UniqueConstraint("organization_id", "id", name="uq_departments_org_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="departments")
    users: Mapped[List["User"]] = relationship("User", back_populates="department")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="department")
