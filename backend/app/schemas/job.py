import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    project_id: uuid.UUID | None
    related_id: uuid.UUID | None
    status: JobStatus
    progress_percent: int
    current_stage: str | None
    logs: list
    error_summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
