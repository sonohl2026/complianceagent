import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    name: str
    legal_name: str | None = None
    website_url: str | None = None
    description: str | None = None
    headquarters: str | None = None
    jurisdictions: list[str] = []


class CompanyUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    website_url: str | None = None
    description: str | None = None
    headquarters: str | None = None
    jurisdictions: list[str] | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    legal_name: str | None
    website_url: str | None
    description: str | None
    headquarters: str | None
    jurisdictions: list[str]
    created_at: datetime
    updated_at: datetime
