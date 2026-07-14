import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import JobStatus, RobotsStatus


class CrawlSnapshot(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "crawl_snapshots"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="crawl_status"), default=JobStatus.QUEUED, nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    crawl_settings_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_snapshots.id", ondelete="SET NULL")
    )

    pages: Mapped[list["CrawledPage"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class CrawledPage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "crawled_pages"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    html_path: Mapped[str | None] = mapped_column(String(1024))
    screenshot_path: Mapped[str | None] = mapped_column(String(1024))
    text_path: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    word_count: Mapped[int | None] = mapped_column(Integer)
    last_modified: Mapped[str | None] = mapped_column(String(255))
    robots_status: Mapped[RobotsStatus] = mapped_column(
        Enum(RobotsStatus, name="robots_status"), default=RobotsStatus.UNKNOWN, nullable=False
    )
    changed_from_prior: Mapped[bool | None] = mapped_column(Boolean)
    change_summary: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    snapshot: Mapped["CrawlSnapshot"] = relationship(back_populates="pages")
