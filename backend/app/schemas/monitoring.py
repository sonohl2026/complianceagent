import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScheduledRecrawlCreate(BaseModel):
    start_url: str
    interval_hours: int = Field(default=24, ge=1, le=8760)
    max_pages: int | None = None
    max_depth: int | None = None
    follow_subdomains: bool = False
    include_pdfs: bool = False


class ScheduledRecrawlUpdate(BaseModel):
    is_active: bool | None = None
    interval_hours: int | None = Field(default=None, ge=1, le=8760)


class ScheduledRecrawlRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    start_url: str
    crawl_settings_json: dict
    interval_hours: int
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime
    created_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    crawl_snapshot_id: uuid.UUID
    canonical_url: str
    category: str
    summary: str
    acknowledged: bool
    created_at: datetime


class AlertWithProject(AlertRead):
    project_name: str
