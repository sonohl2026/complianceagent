import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    product_type: str | None = None
    regulatory_stage: str | None = None
    fda_status: str | None = None
    intended_use: str | None = None
    indications_for_use: str | None = None
    target_population: str | None = None
    intended_user: str | None = None
    site_of_service: str | None = None
    care_setting: str | None = None
    clinical_output: str | None = None
    ai_role: str | None = None
    hardware_version: str | None = None
    software_version: str | None = None
    model_version: str | None = None


class ProductUpdate(ProductCreate):
    name: str | None = None  # type: ignore[assignment]


class ProductRename(BaseModel):
    name: str


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    name_manually_set: bool
    description: str | None
    product_type: str | None
    regulatory_stage: str | None
    fda_status: str | None
    intended_use: str | None
    indications_for_use: str | None
    target_population: str | None
    intended_user: str | None
    site_of_service: str | None
    care_setting: str | None
    clinical_output: str | None
    ai_role: str | None
    hardware_version: str | None
    software_version: str | None
    model_version: str | None
    created_at: datetime
    updated_at: datetime
