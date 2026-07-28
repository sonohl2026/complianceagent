import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class Product(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "products"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Set once a user renames this product (see api/v1/products.py::rename_product).
    # Makes the rename sticky -- quick_scan_tasks.py::_sync_product_name_from_result
    # skips products with this set, rather than overwriting a deliberate rename
    # with whatever Stage 3 resolves on the next scan.
    name_manually_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str | None] = mapped_column(String(255))
    regulatory_stage: Mapped[str | None] = mapped_column(String(64))
    fda_status: Mapped[str | None] = mapped_column(String(255))
    intended_use: Mapped[str | None] = mapped_column(Text)
    indications_for_use: Mapped[str | None] = mapped_column(Text)
    target_population: Mapped[str | None] = mapped_column(Text)
    intended_user: Mapped[str | None] = mapped_column(Text)
    site_of_service: Mapped[str | None] = mapped_column(String(255))
    care_setting: Mapped[str | None] = mapped_column(String(255))
    clinical_output: Mapped[str | None] = mapped_column(Text)
    ai_role: Mapped[str | None] = mapped_column(String(64))
    hardware_version: Mapped[str | None] = mapped_column(String(128))
    software_version: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(128))
    status_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )

    company: Mapped["Company"] = relationship(back_populates="products")
    projects: Mapped[list["Project"]] = relationship(back_populates="default_product")
