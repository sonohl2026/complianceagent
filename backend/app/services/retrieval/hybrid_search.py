"""Hybrid retrieval: pgvector cosine similarity + Postgres full-text search,
combined via reciprocal-rank fusion and boosted by authority level.

Never lets raw semantic similarity alone decide ranking (build spec §12.2) —
see app.services.retrieval.fusion for the boost math.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuthorityLevel, CollectionType, ConfidentialityLevel
from app.models.source_chunk import SourceChunk
from app.models.source_document import SourceDocument
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.sentence_transformer_provider import get_embedding_provider
from app.services.retrieval.fusion import apply_authority_boost, rank_ids, reciprocal_rank_fusion

DEFAULT_CANDIDATE_K = 50


@dataclass
class RetrievalFilter:
    project_id: uuid.UUID | None = None
    collection_types: list[CollectionType] | None = None
    jurisdiction: str | None = None
    document_category: str | None = None
    authority_levels: list[AuthorityLevel] | None = None
    current_only: bool = True
    exclude_confidentiality: list[ConfidentialityLevel] = field(
        default_factory=lambda: [ConfidentialityLevel.RESTRICTED]
    )


@dataclass
class RetrievedChunk:
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
    # Human/system-verified source URL (crawled page URL, or manually entered
    # against an authority-library document) -- never populated from the
    # LLM's own output, since a model could easily fabricate a plausible but
    # fake or dead government URL.
    document_url: str | None = None


def _apply_filters(query, filters: RetrievalFilter):
    query = query.join(SourceDocument, SourceChunk.document_id == SourceDocument.id)
    if filters.project_id is not None:
        # Authority-library documents are shared (project_id IS NULL) and
        # must remain visible from every project's retrieval bundle -- only
        # project-scoped COMPANY/THIRD_PARTY/COMPETITOR documents are
        # restricted to this specific project (build spec §3.3, §12.3).
        query = query.where(
            or_(
                SourceDocument.project_id == filters.project_id,
                SourceDocument.collection_type == CollectionType.AUTHORITY,
            )
        )
    if filters.collection_types:
        query = query.where(SourceDocument.collection_type.in_(filters.collection_types))
    if filters.jurisdiction:
        query = query.where(SourceDocument.jurisdiction == filters.jurisdiction)
    if filters.document_category:
        query = query.where(SourceDocument.document_category == filters.document_category)
    if filters.authority_levels:
        query = query.where(SourceDocument.authority_level.in_(filters.authority_levels))
    if filters.current_only:
        query = query.where(SourceDocument.is_current.is_(True))
    if filters.exclude_confidentiality:
        query = query.where(SourceDocument.confidentiality_level.notin_(filters.exclude_confidentiality))
    return query


def build_vector_candidate_query(query_embedding: list[float], filters: RetrievalFilter, limit: int):
    distance = SourceChunk.embedding.cosine_distance(query_embedding)
    stmt = select(SourceChunk.id, SourceDocument.authority_level).where(
        SourceChunk.embedding.is_not(None)
    )
    stmt = _apply_filters(stmt, filters)
    return stmt.order_by(distance.asc()).limit(limit)


def build_fulltext_candidate_query(query_text: str, filters: RetrievalFilter, limit: int):
    tsquery = func.plainto_tsquery("english", query_text)
    stmt = select(SourceChunk.id, SourceDocument.authority_level).where(
        SourceChunk.search_vector.is_not(None),
        SourceChunk.search_vector.op("@@")(tsquery),
    )
    stmt = _apply_filters(stmt, filters)
    return stmt.order_by(func.ts_rank(SourceChunk.search_vector, tsquery).desc()).limit(limit)


async def hybrid_search(
    db: AsyncSession,
    query_text: str,
    filters: RetrievalFilter | None = None,
    *,
    top_k: int = 10,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunk]:
    filters = filters or RetrievalFilter()
    provider = embedding_provider or get_embedding_provider()
    query_embedding = provider.embed_query(query_text)

    vector_rows = (await db.execute(build_vector_candidate_query(query_embedding, filters, candidate_k))).all()
    fulltext_rows = (
        await db.execute(build_fulltext_candidate_query(query_text, filters, candidate_k))
    ).all()

    vector_ids = [str(row[0]) for row in vector_rows]
    fulltext_ids = [str(row[0]) for row in fulltext_rows]

    authority_by_id: dict[str, AuthorityLevel | None] = {}
    for chunk_id, authority_level in [*vector_rows, *fulltext_rows]:
        authority_by_id[str(chunk_id)] = authority_level

    fused = reciprocal_rank_fusion(vector_ids, fulltext_ids)
    boosted = apply_authority_boost(fused, authority_by_id)
    ordered_ids = rank_ids(boosted)[:top_k]
    if not ordered_ids:
        return []

    uuid_ids = [uuid.UUID(i) for i in ordered_ids]
    result = await db.execute(
        select(SourceChunk, SourceDocument)
        .join(SourceDocument, SourceChunk.document_id == SourceDocument.id)
        .where(SourceChunk.id.in_(uuid_ids))
    )
    rows_by_id = {str(chunk.id): (chunk, document) for chunk, document in result.all()}

    retrieved: list[RetrievedChunk] = []
    for chunk_id in ordered_ids:
        row = rows_by_id.get(chunk_id)
        if row is None:
            continue
        chunk, document = row
        retrieved.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                document_url=document.url,
                collection_type=document.collection_type,
                authority_level=document.authority_level,
                text=chunk.text,
                citation_label=chunk.citation_label,
                page_number=chunk.page_number,
                heading_path=chunk.heading_path,
                score=boosted[chunk_id],
            )
        )
    return retrieved
