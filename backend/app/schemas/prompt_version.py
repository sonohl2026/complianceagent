import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PromptVersionSummary(BaseModel):
    """List view -- no `content`, since the master prompt can be tens of
    thousands of words and callers usually just need version/activity
    metadata, not the full text on every list request."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_label: str
    is_active: bool
    change_summary: str | None
    created_at: datetime


class PromptVersionDetail(PromptVersionSummary):
    content: str
    word_count: int
    character_count: int
