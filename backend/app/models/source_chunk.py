import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin

# Must match config.local_embedding_model's output dimensionality
# (sentence-transformers/all-MiniLM-L6-v2 -> 384). Changing the embedding
# model requires a migration + full reindex (scripts/reindex_project.py).
EMBEDDING_DIM = 384


class SourceChunk(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "source_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(512))
    heading_path: Mapped[str | None] = mapped_column(String(1024))
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
    citation_label: Mapped[str] = mapped_column(String(512), nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    document: Mapped["SourceDocument"] = relationship(back_populates="chunks")
