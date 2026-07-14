import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatCitation(BaseModel):
    role: str
    document_title: str | None
    section_title: str | None
    page_number: int | None
    url: str | None
    quoted_text: str | None


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    role: str
    content: str
    citations_json: list[ChatCitation]
    created_at: datetime


class ChatQuestionRequest(BaseModel):
    question: str
