import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ClaimCategory, ClaimDisposition, EvidenceStatus, ExpressOrImplied, RiskLevel


class ExtractedClaim(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "extracted_claims"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    source_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_chunks.id", ondelete="SET NULL")
    )
    exact_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_category: Mapped[ClaimCategory] = mapped_column(Enum(ClaimCategory, name="claim_category"), nullable=False)
    express_or_implied: Mapped[ExpressOrImplied] = mapped_column(
        Enum(ExpressOrImplied, name="express_or_implied"), nullable=False
    )
    audience: Mapped[str | None] = mapped_column(String(255))
    evidence_status: Mapped[EvidenceStatus] = mapped_column(
        Enum(EvidenceStatus, name="claim_evidence_status"), nullable=False
    )
    intended_use_alignment: Mapped[str | None] = mapped_column(String(64))
    regulatory_status_alignment: Mapped[str | None] = mapped_column(String(64))
    risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="claim_risk"), nullable=False)
    recommended_disposition: Mapped[ClaimDisposition] = mapped_column(
        Enum(ClaimDisposition, name="claim_disposition"), nullable=False
    )
    proposed_replacement: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(32), default="PENDING_REVIEW", nullable=False)
