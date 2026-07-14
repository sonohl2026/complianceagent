import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class ScheduledRecrawl(UUIDPKMixin, TimestampMixin, Base):
    """A recurring recrawl (Milestone 8). Celery Beat's
    monitoring.dispatch_due_recrawls task (runs every 30 minutes, see
    app.workers.celery_app) enqueues the same crawling.run_crawl task a
    manual crawl uses whenever next_run_at has passed, then advances
    next_run_at by interval_hours -- no separate scheduled-crawl execution
    path, just automated dispatch of the existing one."""

    __tablename__ = "scheduled_recrawls"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    start_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    crawl_settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Alert(UUIDPKMixin, TimestampMixin, Base):
    """A material change flagged after a *scheduled* recrawl (build spec
    §10.4: deterministic hash diffing decides whether a page changed at
    all -- app.services.crawling.diff -- an LLM pass decides only whether an
    already-detected change is material, never whether something changed in
    the first place). Manual one-off crawls don't generate alerts; only
    scheduled monitoring does, to keep this additive to existing crawl cost/
    behavior rather than changing it."""

    __tablename__ = "alerts"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    crawl_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
