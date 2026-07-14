import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import FindingDomain, JobStatus, RiskLevel, Verdict


class AnalysisRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "analysis_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )
    analysis_type: Mapped[str] = mapped_column(String(64), default="FULL_COMPLIANCE_ANALYSIS")
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="analysis_status"), default=JobStatus.QUEUED, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    system_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_versions.id", ondelete="SET NULL")
    )
    analysis_model: Mapped[str | None] = mapped_column(String(255))
    model_provider: Mapped[str] = mapped_column(String(64), default="openrouter")
    model_response_identifier: Mapped[str | None] = mapped_column(String(255))
    source_cutoff_date: Mapped[date | None] = mapped_column(Date)
    input_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    overall_verdict: Mapped[Verdict | None] = mapped_column(Enum(Verdict, name="verdict"))
    overall_risk: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel, name="risk_level"))
    readiness_score: Mapped[int | None] = mapped_column(Integer)
    # Set only when app.services.analysis.scoring::apply_readiness_score_guardrail
    # lowered the model's own reported score to respect a hard internal-
    # consistency rule (e.g. a STOP verdict can't coexist with a high
    # readiness score) -- explains *why* readiness_score isn't simply
    # whatever the model said, without hiding what the model said (the
    # original number is quoted in the note text itself).
    readiness_score_note: Mapped[str | None] = mapped_column(Text)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    critical_blockers: Mapped[list] = mapped_column(ARRAY(String), default=list)
    missing_inputs: Mapped[list] = mapped_column(ARRAY(String), default=list)
    priority_actions: Mapped[list] = mapped_column(ARRAY(String), default=list)
    required_reviewers: Mapped[list] = mapped_column(ARRAY(String), default=list)

    token_usage_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    cost_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    current_stage: Mapped[str | None] = mapped_column(String(128))

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="analysis_run", cascade="all, delete-orphan"
    )


class Finding(UUIDPKMixin, Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[FindingDomain] = mapped_column(Enum(FindingDomain, name="finding_domain"), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    finding_type: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # EvidenceStatus value
    risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="finding_risk"), nullable=False)
    verdict: Mapped[Verdict | None] = mapped_column(Enum(Verdict, name="finding_verdict"))
    verified_fact: Mapped[str | None] = mapped_column(Text)
    missing_information: Mapped[list] = mapped_column(ARRAY(String), default=list)
    applicable_requirement: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)
    responsible_owner: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[int | None] = mapped_column(Integer)
    due_timing: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[int | None] = mapped_column(Integer)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis_run: Mapped["AnalysisRun"] = relationship(back_populates="findings")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )
