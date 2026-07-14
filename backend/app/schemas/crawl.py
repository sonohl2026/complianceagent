import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import JobStatus, RobotsStatus


class CrawlCreateRequest(BaseModel):
    start_url: str
    max_pages: int | None = Field(default=None, ge=1, le=2000)
    max_depth: int | None = Field(default=None, ge=0, le=10)
    follow_subdomains: bool = False
    include_pdfs: bool = False
    inclusion_patterns: list[str] = []
    exclusion_patterns: list[str] = []
    render_js: bool = False
    rerun_from_previous: bool = True


class CrawlSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    root_url: str
    started_at: datetime | None
    completed_at: datetime | None
    status: JobStatus
    page_count: int
    crawl_settings_json: dict
    error_summary: str | None
    previous_snapshot_id: uuid.UUID | None
    created_at: datetime


class CrawlSnapshotWithProject(CrawlSnapshotRead):
    project_name: str


class CrawledPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    canonical_url: str
    title: str | None
    http_status: int | None
    content_type: str | None
    sha256: str | None
    word_count: int | None
    robots_status: RobotsStatus
    changed_from_prior: bool | None
    change_summary: str | None
    source_document_id: uuid.UUID | None


class CrawlDiffEntry(BaseModel):
    canonical_url: str
    change_type: str
    old_title: str | None = None
    new_title: str | None = None


class CrawlDiffResponse(BaseModel):
    previous_snapshot_id: uuid.UUID | None
    current_snapshot_id: uuid.UUID
    summary: dict[str, int]
    entries: list[CrawlDiffEntry]
