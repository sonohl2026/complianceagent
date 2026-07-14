import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class Project(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    jurisdiction: Mapped[str | None] = mapped_column(String(255), default="United States")
    target_payers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    analysis_scope: Mapped[str | None] = mapped_column(Text)
    # FK to prompt_versions.id added in Milestone 5 once that table exists.
    system_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    company: Mapped["Company"] = relationship(back_populates="projects")
    default_product: Mapped["Product | None"] = relationship(back_populates="projects")
    documents: Mapped[list["SourceDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
