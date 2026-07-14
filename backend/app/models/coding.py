import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import CodingEligibilityStatus


class CodingCandidate(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "coding_candidates"

    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    code_system: Mapped[str] = mapped_column(String(64), nullable=False)
    # code/code_year are Text, not a short VARCHAR, for the same reason as
    # coverage/payment/billing_status below: when the model can't determine
    # a concrete code or FY year, it writes an explanatory disclaimer (e.g.
    # "[CURRENT-SOURCE VERIFICATION REQUIRED: confirm applicable FY ICD-10-PCS
    # code set]") into the field rather than leaving it blank -- a real
    # incident, seen in production, that overflowed a VARCHAR(16) code_year
    # column and crashed the whole analysis.
    code: Mapped[str | None] = mapped_column(Text)
    code_year: Mapped[str | None] = mapped_column(Text)
    descriptor_reference: Mapped[str | None] = mapped_column(Text)
    service_definition: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_status: Mapped[CodingEligibilityStatus] = mapped_column(
        Enum(CodingEligibilityStatus, name="coding_eligibility_status"), nullable=False
    )
    # Free-text explanatory status (e.g. "UNDETERMINED -- coverage is payer-
    # and policy-specific and cannot be assessed without verified FDA status
    # [CURRENT-SOURCE VERIFICATION REQUIRED]"), not a short code -- the
    # master prompt's philosophy is to explain *why* something is unresolved
    # rather than collapse it to a terse label, so these must be unbounded.
    coverage_status: Mapped[str | None] = mapped_column(Text)
    payment_status: Mapped[str | None] = mapped_column(Text)
    billing_status: Mapped[str | None] = mapped_column(Text)
    major_gaps: Mapped[list] = mapped_column(ARRAY(String), default=list)
    expert_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    requirements: Mapped[list["CodingRequirement"]] = relationship(
        back_populates="coding_candidate", cascade="all, delete-orphan"
    )


class CodingRequirement(UUIDPKMixin, Base):
    __tablename__ = "coding_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coding_candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coding_candidates.id", ondelete="CASCADE"), nullable=False
    )
    requirement_name: Mapped[str] = mapped_column(String(255), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    verified_company_fact: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # EvidenceStatus value
    company_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    authority_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    gap: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(255))

    coding_candidate: Mapped["CodingCandidate"] = relationship(back_populates="requirements")
