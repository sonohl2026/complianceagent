import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExtractedClaimRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source_document_id: uuid.UUID | None
    source_chunk_id: uuid.UUID | None
    exact_text: str
    claim_category: str
    express_or_implied: str
    audience: str | None
    evidence_status: str
    intended_use_alignment: str | None
    regulatory_status_alignment: str | None
    risk: str
    recommended_disposition: str
    proposed_replacement: str | None
    review_status: str
    created_at: datetime


class ExtractedClaimWithProject(ExtractedClaimRead):
    project_name: str


class ExtractedClaimUpdate(BaseModel):
    review_status: str
