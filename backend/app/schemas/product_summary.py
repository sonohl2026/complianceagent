import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import JobStatus


class ProductSummary(BaseModel):
    """One row of the Products list (MVP lockdown Step 1's home page) --
    just enough of the latest quick_scan run to sort/scan by without pulling
    the full result payload for every product."""

    id: uuid.UUID
    name: str
    updated_at: datetime
    latest_run_id: uuid.UUID | None
    latest_run_status: JobStatus | None
    latest_run_created_at: datetime | None
    maturity: int | None
    maturity_state: str | None
    risk_flag: str | None
