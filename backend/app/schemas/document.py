import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import AuthorityLevel, CollectionType, ConfidentialityLevel, EmbeddingStatus, ParseStatus


def _require_http_scheme(url: str | None) -> str | None:
    # Report exports turn this into a real <a href>/Markdown link, so a
    # non-http(s) scheme here (e.g. "javascript:...") would be a stored-XSS
    # vector the moment someone views the report -- reject at the boundary
    # where a human enters it, not just at render time.
    if url and not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Source URL must start with http:// or https://")
    return url


class SourceDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    collection_type: CollectionType
    source_type: str | None
    authority_level: AuthorityLevel | None
    title: str
    issuer: str | None
    url: str | None
    original_filename: str | None
    mime_type: str | None
    jurisdiction: str | None
    document_category: str | None
    publication_date: date | None
    effective_date: date | None
    expiration_date: date | None
    version: str | None
    is_current: bool
    is_superseded: bool
    sha256: str | None
    parse_status: ParseStatus
    embedding_status: EmbeddingStatus
    confidentiality_level: ConfidentialityLevel
    parse_error: str | None
    created_at: datetime
    updated_at: datetime


class SourceDocumentMetadataUpdate(BaseModel):
    title: str | None = None
    issuer: str | None = None
    url: str | None = None
    jurisdiction: str | None = None
    document_category: str | None = None
    source_type: str | None = None
    authority_level: AuthorityLevel | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    version: str | None = None
    is_current: bool | None = None
    confidentiality_level: ConfidentialityLevel | None = None

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        return _require_http_scheme(value)


class SourceDocumentWithProject(SourceDocumentRead):
    project_name: str | None


class SourceChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    text: str
    token_count: int | None
    page_number: int | None
    section_title: str | None
    heading_path: str | None
    citation_label: str
