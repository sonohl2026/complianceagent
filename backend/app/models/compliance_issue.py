import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ComplianceIssueStatus, FindingDomain, RiskLevel


class ComplianceIssue(UUIDPKMixin, TimestampMixin, Base):
    """A durable, product-level compliance issue tracked across analysis
    runs -- unlike Finding (scoped to one AnalysisRun), this persists so a
    re-run after a small site/document tweak can show what's still open vs.
    what got fixed, instead of forcing a full re-read of a new report every
    time (user-requested; see docs/data-model.md).

    Legacy: populated by the old document-driven pipeline (now removed) via
    a normalized-title + domain equality check against each run's findings.
    Historical rows remain and still render in ComplianceChecklist.tsx, but
    nothing writes new ones now that pipeline is gone."""

    __tablename__ = "compliance_issues"

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[FindingDomain] = mapped_column(
        Enum(FindingDomain, name="compliance_issue_domain"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="compliance_issue_risk"), nullable=False)
    status: Mapped[ComplianceIssueStatus] = mapped_column(
        Enum(ComplianceIssueStatus, name="compliance_issue_status"),
        default=ComplianceIssueStatus.OPEN,
        nullable=False,
    )
    first_detected_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    last_seen_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    resolved_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
