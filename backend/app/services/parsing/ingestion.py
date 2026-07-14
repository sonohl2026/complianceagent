"""End-to-end document ingestion: validate -> store -> parse -> chunk -> persist.

This is deliberately synchronous/sequential and framework-agnostic (plain
`AsyncSession` in, list of created rows out) so it can be invoked either from
a Celery task (real usage) or directly from a test, without duplicating
logic in two places.
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuthorityLevel, CollectionType, ConfidentialityLevel, EmbeddingStatus, ParseStatus
from app.models.source_chunk import SourceChunk
from app.models.source_document import SourceDocument
from app.services.parsing.base import ParsingError
from app.services.parsing.chunking import chunk_document
from app.services.parsing.dispatch import parse_document
from app.services.parsing.validation import UploadValidationError, validate_upload
from app.services.storage.file_storage import StorageBackend, get_storage, sanitize_filename


@dataclass
class IngestionResult:
    document: SourceDocument
    chunk_count: int
    duplicate_of: SourceDocument | None = None


async def ingest_upload(
    db: AsyncSession,
    *,
    filename: str,
    content: bytes,
    project_id,
    collection_type: CollectionType,
    confidentiality_level: ConfidentialityLevel = ConfidentialityLevel.INTERNAL,
    title: str | None = None,
    issuer: str | None = None,
    jurisdiction: str | None = None,
    authority_level: AuthorityLevel | None = None,
    source_type: str | None = None,
    url: str | None = None,
    storage: StorageBackend | None = None,
) -> IngestionResult:
    storage = storage or get_storage()
    safe_name = sanitize_filename(filename)

    try:
        validated = validate_upload(filename, content)
    except UploadValidationError as exc:
        quarantine_path = storage.save_bytes("quarantine", content, suffix=f"-{safe_name}")
        document = SourceDocument(
            project_id=project_id,
            collection_type=collection_type,
            title=title or safe_name,
            original_filename=safe_name,
            local_path=quarantine_path,
            confidentiality_level=confidentiality_level,
            parse_status=ParseStatus.QUARANTINED,
            embedding_status=EmbeddingStatus.FAILED,
            parse_error=exc.reason,
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        return IngestionResult(document=document, chunk_count=0)

    sha256 = hashlib.sha256(content).hexdigest()

    existing = await db.scalar(
        select(SourceDocument).where(
            SourceDocument.sha256 == sha256,
            SourceDocument.project_id == project_id,
            SourceDocument.parse_status != ParseStatus.QUARANTINED,
        )
    )

    stored_path = storage.save_bytes("uploads", content, suffix=validated.extension)

    document = SourceDocument(
        project_id=project_id,
        collection_type=collection_type,
        title=title or safe_name,
        issuer=issuer,
        jurisdiction=jurisdiction,
        authority_level=authority_level,
        source_type=source_type,
        url=url,
        original_filename=safe_name,
        local_path=stored_path,
        mime_type=validated.mime_type,
        sha256=sha256,
        confidentiality_level=confidentiality_level,
        parse_status=ParseStatus.PROCESSING,
        embedding_status=EmbeddingStatus.PENDING,
    )
    db.add(document)
    await db.flush()

    try:
        parsed = parse_document(validated.extension, content)
    except ParsingError as exc:
        document.parse_status = ParseStatus.FAILED
        document.parse_error = str(exc)
        await db.commit()
        await db.refresh(document)
        return IngestionResult(
            document=document, chunk_count=0, duplicate_of=existing if existing else None
        )

    if parsed.title and not title:
        document.title = parsed.title

    chunks = chunk_document(parsed, document.title)
    for chunk in chunks:
        db.add(
            SourceChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                token_count=chunk.token_count,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                heading_path=chunk.heading_path,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                citation_label=chunk.citation_label,
            )
        )

    document.parse_status = ParseStatus.COMPLETE
    await db.commit()
    await db.refresh(document)

    return IngestionResult(document=document, chunk_count=len(chunks), duplicate_of=existing)


async def ingest_crawled_html(
    db: AsyncSession,
    *,
    project_id,
    url: str,
    html: bytes,
    title: str | None = None,
    storage: StorageBackend | None = None,
) -> IngestionResult:
    """Same parse -> chunk -> persist path as ingest_upload, but for crawler
    output rather than a user-uploaded file: no MIME/executable validation
    (the crawler already knows this is HTML from the response content-type
    and enforces its own size limit), stored under the crawled page's URL as
    its citation source rather than an uploaded filename."""
    storage = storage or get_storage()
    sha256 = hashlib.sha256(html).hexdigest()

    existing = await db.scalar(
        select(SourceDocument).where(
            SourceDocument.sha256 == sha256,
            SourceDocument.project_id == project_id,
            SourceDocument.parse_status != ParseStatus.QUARANTINED,
        )
    )

    stored_path = storage.save_bytes("crawls", html, suffix=".html")

    document = SourceDocument(
        project_id=project_id,
        collection_type=CollectionType.COMPANY,
        source_type="website_page",
        title=title or url,
        url=url,
        mime_type="text/html",
        sha256=sha256,
        confidentiality_level=ConfidentialityLevel.INTERNAL,
        parse_status=ParseStatus.PROCESSING,
        embedding_status=EmbeddingStatus.PENDING,
    )
    db.add(document)
    await db.flush()

    try:
        parsed = parse_document(".html", html)
    except ParsingError as exc:
        document.parse_status = ParseStatus.FAILED
        document.parse_error = str(exc)
        await db.commit()
        await db.refresh(document)
        return IngestionResult(document=document, chunk_count=0, duplicate_of=existing)

    if parsed.title and not title:
        document.title = parsed.title

    chunks = chunk_document(parsed, document.title)
    for chunk in chunks:
        db.add(
            SourceChunk(
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                token_count=chunk.token_count,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                heading_path=chunk.heading_path,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                citation_label=chunk.citation_label,
            )
        )

    document.parse_status = ParseStatus.COMPLETE
    await db.commit()
    await db.refresh(document)

    return IngestionResult(document=document, chunk_count=len(chunks), duplicate_of=existing)
