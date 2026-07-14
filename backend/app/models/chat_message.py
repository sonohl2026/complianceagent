import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class ChatMessage(UUIDPKMixin, TimestampMixin, Base):
    """A minimal project-scoped Q&A history (Milestone 7). Deliberately not
    a full agentic conversation: each question gets exactly one retrieval +
    one structured-output LLM call (same cost profile as a single pipeline
    stage, not the full 7-stage analysis), grounded only in this project's
    evidence plus the shared Authority Library -- never a substitute for
    running the full compliance analysis pipeline."""

    __tablename__ = "chat_messages"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Each item: {role, document_title, section_title, page_number, url,
    # quoted_text} -- same shape as a resolved pipeline Citation, but kept
    # as JSON here rather than relational rows since chat messages have no
    # analysis_run_id to hang a Citation off of.
    citations_json: Mapped[list] = mapped_column(JSONB, default=list)
