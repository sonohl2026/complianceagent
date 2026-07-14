import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPKMixin
from app.models.enums import CitationRole, CitationVerificationStatus


class Citation(UUIDPKMixin, Base):
    __tablename__ = "citations"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_chunks.id", ondelete="SET NULL")
    )
    citation_role: Mapped[CitationRole] = mapped_column(Enum(CitationRole, name="citation_role"), nullable=False)
    quoted_text: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(2048))
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supports_claim: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verification_status: Mapped[CitationVerificationStatus] = mapped_column(
        Enum(CitationVerificationStatus, name="citation_verification_status"),
        default=CitationVerificationStatus.UNVERIFIED,
        nullable=False,
    )

    finding: Mapped["Finding"] = relationship(back_populates="citations")
