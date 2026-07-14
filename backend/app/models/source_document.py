import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import AuthorityLevel, CollectionType, ConfidentialityLevel, EmbeddingStatus, ParseStatus


class SourceDocument(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"

    # Nullable: AUTHORITY documents are shared across projects, not scoped to one.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )

    collection_type: Mapped[CollectionType] = mapped_column(
        Enum(CollectionType, name="collection_type"), nullable=False
    )
    source_type: Mapped[str | None] = mapped_column(String(128))
    authority_level: Mapped[AuthorityLevel | None] = mapped_column(
        Enum(AuthorityLevel, name="authority_level")
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2048))
    local_path: Mapped[str | None] = mapped_column(String(1024))
    mime_type: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str | None] = mapped_column(String(512))

    jurisdiction: Mapped[str | None] = mapped_column(String(255))
    document_category: Mapped[str | None] = mapped_column(String(255))

    publication_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiration_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    version: Mapped[str | None] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(default=True)
    is_superseded: Mapped[bool] = mapped_column(default=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_documents.id", ondelete="SET NULL")
    )

    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus, name="parse_status"), default=ParseStatus.PENDING, nullable=False
    )
    embedding_status: Mapped[EmbeddingStatus] = mapped_column(
        Enum(EmbeddingStatus, name="embedding_status"),
        default=EmbeddingStatus.PENDING,
        nullable=False,
    )
    confidentiality_level: Mapped[ConfidentialityLevel] = mapped_column(
        Enum(ConfidentialityLevel, name="confidentiality_level"),
        default=ConfidentialityLevel.INTERNAL,
        nullable=False,
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    project: Mapped["Project | None"] = relationship(back_populates="documents")
    chunks: Mapped[list["SourceChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="SourceChunk.chunk_index"
    )
