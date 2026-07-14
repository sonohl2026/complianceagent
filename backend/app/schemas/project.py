import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    company_id: uuid.UUID
    name: str
    description: str | None = None
    default_product_id: uuid.UUID | None = None
    jurisdiction: str | None = "United States"
    target_payers: list[str] = []
    analysis_scope: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    default_product_id: uuid.UUID | None = None
    jurisdiction: str | None = None
    target_payers: list[str] | None = None
    analysis_scope: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: str | None
    default_product_id: uuid.UUID | None
    jurisdiction: str | None
    target_payers: list[str]
    analysis_scope: str | None
    created_at: datetime
    updated_at: datetime
