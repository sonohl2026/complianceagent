import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ComplianceIssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    domain: str
    title: str
    description: str
    risk: str
    status: str
    first_detected_run_id: uuid.UUID | None
    last_seen_run_id: uuid.UUID | None
    resolved_run_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
