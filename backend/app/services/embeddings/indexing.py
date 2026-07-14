"""Populate SourceChunk.embedding and SourceChunk.search_vector for a document.

Called from the ingestion pipeline right after chunks are persisted, and
from scripts/reindex_project.py after an embedding-model change.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import EmbeddingStatus
from app.models.source_chunk import SourceChunk
from app.models.source_document import SourceDocument
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.sentence_transformer_provider import get_embedding_provider


async def embed_document(
    db: AsyncSession,
    document: SourceDocument,
    *,
    provider: EmbeddingProvider | None = None,
) -> int:
    """Embed every chunk of `document` and populate full-text search vectors.
    Returns the number of chunks embedded. Safe to call more than once
    (re-embeds unconditionally, which is what a reindex needs)."""
    provider = provider or get_embedding_provider()

    result = await db.execute(
        select(SourceChunk).where(SourceChunk.document_id == document.id).order_by(SourceChunk.chunk_index)
    )
    chunks = list(result.scalars().all())
    if not chunks:
        document.embedding_status = EmbeddingStatus.COMPLETE
        await db.commit()
        return 0

    document.embedding_status = EmbeddingStatus.PROCESSING
    await db.commit()

    try:
        vectors = provider.embed_documents([c.text for c in chunks])
        embedded_at = datetime.now(timezone.utc).isoformat()

        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
            chunk.metadata_json = {
                **(chunk.metadata_json or {}),
                "embedding_model": provider.info.name,
                "embedding_dimensions": provider.info.dimensions,
                "embedded_at": embedded_at,
            }

        # search_vector requires a Postgres-side to_tsvector() call, not a
        # Python-computable value -- issued as a single bulk UPDATE.
        await db.execute(
            update(SourceChunk)
            .where(SourceChunk.document_id == document.id)
            .values(search_vector=func.to_tsvector("english", SourceChunk.text))
        )

        document.embedding_status = EmbeddingStatus.COMPLETE
        await db.commit()
        return len(chunks)
    except Exception:
        document.embedding_status = EmbeddingStatus.FAILED
        await db.commit()
        raise
