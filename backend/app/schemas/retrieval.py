import uuid

from pydantic import BaseModel, Field

from app.models.enums import AuthorityLevel, CollectionType


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    collection_types: list[CollectionType] | None = None


class SearchResultChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    collection_type: CollectionType
    authority_level: AuthorityLevel | None
    text: str
    citation_label: str
    page_number: int | None
    heading_path: str | None
    score: float
