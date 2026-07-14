"""Layers an LLM material-change classification on top of the deterministic
hash-diffing crawler.py already does (build spec §10.4: never let the LLM
decide *whether* something changed -- only whether an already-detected
change is material). Only runs for scheduled recrawls, not manual one-off
crawls (see app/workers/crawl_tasks.py), so it's additive to existing crawl
cost/behavior rather than a change to it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawledPage, CrawlSnapshot
from app.models.enums import CollectionType
from app.models.monitoring import Alert
from app.models.source_chunk import SourceChunk
from app.schemas.monitoring_llm import MaterialChangeAssessmentResult
from app.services.analysis.prompt_composer import compose_messages
from app.services.analysis.prompts_service import get_active_master_prompt, load_module_prompt
from app.services.llm.base import LLMProvider
from app.services.retrieval.hybrid_search import RetrievedChunk
from app.services.storage.settings_store import load_runtime_settings

MAX_PAGES_PER_ASSESSMENT = 20
EXCERPT_CHARS = 2000
MATERIAL_CHANGE_MAX_TOKENS = 6000


async def _page_text_excerpt(db: AsyncSession, source_document_id: uuid.UUID | None) -> str:
    if source_document_id is None:
        return "[no text captured for this page]"
    rows = (
        await db.execute(
            select(SourceChunk.text)
            .where(SourceChunk.document_id == source_document_id)
            .order_by(SourceChunk.chunk_index)
            .limit(5)
        )
    ).all()
    text = "\n\n".join(row[0] for row in rows)
    return text[:EXCERPT_CHARS] or "[no text captured for this page]"


def _synthetic_chunk(label: str, text: str) -> RetrievedChunk:
    # Not a real hybrid_search result -- reuses RetrievedChunk purely so this
    # can go through compose_messages' proven BEGIN/END UNTRUSTED SOURCE
    # CONTENT wrapping (crawled page text is exactly the kind of untrusted
    # content that boundary exists for) instead of hand-rolling a second,
    # untested wrapping mechanism.
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=label,
        collection_type=CollectionType.COMPANY,
        authority_level=None,
        text=text,
        citation_label=label,
        page_number=None,
        heading_path=None,
        score=1.0,
    )


async def assess_material_changes(
    db: AsyncSession, llm: LLMProvider, model: str, snapshot: CrawlSnapshot
) -> list[Alert]:
    if snapshot.previous_snapshot_id is None:
        return []

    changed_pages = (
        await db.execute(
            select(CrawledPage)
            .where(CrawledPage.snapshot_id == snapshot.id, CrawledPage.changed_from_prior.is_(True))
            .limit(MAX_PAGES_PER_ASSESSMENT)
        )
    ).scalars().all()
    if not changed_pages:
        return []

    previous_pages = (
        await db.execute(select(CrawledPage).where(CrawledPage.snapshot_id == snapshot.previous_snapshot_id))
    ).scalars().all()
    previous_by_url = {p.canonical_url: p for p in previous_pages}

    evidence_chunks: list[RetrievedChunk] = []
    for page in changed_pages:
        old_page = previous_by_url.get(page.canonical_url)
        old_excerpt = await _page_text_excerpt(db, old_page.source_document_id if old_page else None)
        new_excerpt = await _page_text_excerpt(db, page.source_document_id)
        evidence_chunks.append(_synthetic_chunk(f"OLD: {page.canonical_url}", old_excerpt))
        evidence_chunks.append(_synthetic_chunk(f"NEW: {page.canonical_url}", new_excerpt))

    settings = load_runtime_settings()
    master_prompt_version = await get_active_master_prompt(db)
    system_prompt, messages = compose_messages(
        master_prompt=master_prompt_version.content,
        module_prompt=load_module_prompt("material_change_assessment"),
        project_facts={"pages_changed": [p.canonical_url for p in changed_pages]},
        evidence_chunks=evidence_chunks,
        enable_prompt_caching=settings.get("openrouter_prompt_caching", True),
    )

    result = await llm.structured_completion(
        system_prompt=system_prompt,
        messages=messages,
        schema=MaterialChangeAssessmentResult.model_json_schema(),
        schema_name="material_change_assessment",
        model=model,
        temperature=0,
        max_tokens=MATERIAL_CHANGE_MAX_TOKENS,
    )
    parsed = MaterialChangeAssessmentResult.model_validate(result.content)

    alerts = []
    for entry in parsed.entries:
        if not entry.is_material:
            continue
        alert = Alert(
            project_id=snapshot.project_id,
            crawl_snapshot_id=snapshot.id,
            canonical_url=entry.canonical_url,
            category=entry.category,
            summary=entry.summary,
        )
        db.add(alert)
        alerts.append(alert)

    if alerts:
        await db.commit()
    return alerts
