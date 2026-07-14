"""Crawl orchestration: BFS over same-domain links, SSRF-guarded fetch,
robots.txt compliance, deterministic diffing against the prior snapshot, and
ingestion of each HTML page into the same SourceDocument/SourceChunk/
embedding pipeline used for uploads (Milestones 2-3) so crawled content is
retrievable identically to an uploaded document.
"""

import asyncio
import hashlib
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawledPage, CrawlSnapshot
from app.models.enums import JobStatus, ParseStatus, RobotsStatus
from app.services.crawling.diff import PageSnapshot, diff_snapshots
from app.services.crawling.extract import extract_page
from app.services.crawling.fetch import FetchError, USER_AGENT, safe_fetch
from app.services.crawling.robots import build_robots_parser, crawl_delay as robots_crawl_delay, is_allowed
from app.services.crawling.ssrf import SSRFBlockedError
from app.services.crawling.url_utils import is_in_crawl_scope, matches_any_pattern, normalize_url
from app.services.embeddings.indexing import embed_document
from app.services.parsing.ingestion import ingest_crawled_html

logger = logging.getLogger(__name__)


@dataclass
class CrawlSettings:
    start_url: str
    max_pages: int = 250
    max_depth: int = 4
    follow_subdomains: bool = False
    include_pdfs: bool = False
    inclusion_patterns: list[str] = field(default_factory=list)
    exclusion_patterns: list[str] = field(default_factory=list)
    crawl_delay_ms: int = 750
    render_js: bool = False  # best-effort Playwright fallback; see crawler.py module note below

    def as_dict(self) -> dict:
        return {
            "start_url": self.start_url,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "follow_subdomains": self.follow_subdomains,
            "include_pdfs": self.include_pdfs,
            "inclusion_patterns": self.inclusion_patterns,
            "exclusion_patterns": self.exclusion_patterns,
            "crawl_delay_ms": self.crawl_delay_ms,
            "render_js": self.render_js,
        }


def should_fetch(url: str, root_hostname: str, settings: CrawlSettings) -> bool:
    """Scope + include/exclude pattern decision, kept as a pure function
    (no HTTP, no robots.txt, no DB) so BFS filtering logic is directly
    unit-testable."""
    if not is_in_crawl_scope(url, root_hostname, follow_subdomains=settings.follow_subdomains):
        return False
    if settings.exclusion_patterns and matches_any_pattern(url, settings.exclusion_patterns):
        return False
    if settings.inclusion_patterns and not matches_any_pattern(url, settings.inclusion_patterns):
        return False
    return True


async def _load_robots(client: httpx.AsyncClient, start_url: str):
    parts = urlsplit(start_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        result = await safe_fetch(client, robots_url, max_bytes=1024 * 1024)
        content = result.content.decode("utf-8", errors="replace") if result.status_code == 200 else None
    except (SSRFBlockedError, FetchError) as exc:
        logger.info("robots.txt fetch failed for %s: %s", robots_url, exc)
        content = None
    return build_robots_parser(content, robots_url)


async def run_crawl(
    db: AsyncSession,
    snapshot: CrawlSnapshot,
    settings: CrawlSettings,
    *,
    progress_callback=None,
) -> None:
    root_hostname = urlsplit(settings.start_url).hostname or ""
    snapshot.status = JobStatus.RUNNING
    snapshot.started_at = datetime.now(timezone.utc)
    await db.commit()

    if settings.render_js:
        logger.info(
            "render_js requested for snapshot %s; JS rendering is a best-effort fallback "
            "not exercised by this crawl (Playwright is not wired into the default path).",
            snapshot.id,
        )

    async with httpx.AsyncClient() as client:
        robots_parser = await _load_robots(client, settings.start_url)

        queue: deque[tuple[str, int]] = deque([(normalize_url(settings.start_url), 0)])
        visited: set[str] = set()
        page_count = 0

        while queue and page_count < settings.max_pages:
            # Cooperative cancellation: POST /crawls/{id}/cancel updates this
            # row from a different session/request, so re-read just the
            # status column each iteration rather than trusting the
            # in-memory object (which would never see the other session's
            # write without an explicit re-fetch).
            current_status = await db.scalar(
                select(CrawlSnapshot.status).where(CrawlSnapshot.id == snapshot.id)
            )
            if current_status == JobStatus.CANCELLED:
                logger.info("Crawl snapshot %s was cancelled; stopping.", snapshot.id)
                return

            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            if not should_fetch(url, root_hostname, settings):
                continue

            if not is_allowed(robots_parser, USER_AGENT, url):
                db.add(
                    CrawledPage(
                        snapshot_id=snapshot.id,
                        url=url,
                        canonical_url=url,
                        robots_status=RobotsStatus.DISALLOWED,
                    )
                )
                await db.commit()
                continue

            try:
                result = await safe_fetch(client, url)
            except (SSRFBlockedError, FetchError) as exc:
                db.add(
                    CrawledPage(
                        snapshot_id=snapshot.id,
                        url=url,
                        canonical_url=url,
                        robots_status=RobotsStatus.ALLOWED,
                        metadata_json={"fetch_error": str(exc)},
                    )
                )
                await db.commit()
                continue

            page_count += 1
            content_type = result.content_type or ""
            sha256 = hashlib.sha256(result.content).hexdigest()

            if "text/html" in content_type:
                html_text = result.content.decode("utf-8", errors="replace")
                extracted = extract_page(html_text, result.final_url)
                canonical_url = normalize_url(extracted.canonical_url or result.final_url)

                ingestion_result = await ingest_crawled_html(
                    db,
                    project_id=snapshot.project_id,
                    url=result.final_url,
                    html=result.content,
                    title=extracted.title,
                )
                if ingestion_result.document.parse_status == ParseStatus.COMPLETE and ingestion_result.chunk_count:
                    await embed_document(db, ingestion_result.document)

                db.add(
                    CrawledPage(
                        snapshot_id=snapshot.id,
                        url=url,
                        canonical_url=canonical_url,
                        title=extracted.title,
                        http_status=result.status_code,
                        content_type=content_type,
                        sha256=sha256,
                        word_count=extracted.word_count,
                        robots_status=RobotsStatus.ALLOWED,
                        source_document_id=ingestion_result.document.id,
                        metadata_json={"meta_description": extracted.meta_description},
                    )
                )

                for link in extracted.links:
                    normalized_link = normalize_url(link)
                    if normalized_link not in visited and depth + 1 <= settings.max_depth:
                        queue.append((normalized_link, depth + 1))
                if settings.include_pdfs:
                    for pdf_link in extracted.pdf_links:
                        normalized_pdf = normalize_url(pdf_link)
                        if normalized_pdf not in visited and depth + 1 <= settings.max_depth:
                            queue.append((normalized_pdf, depth + 1))
            else:
                db.add(
                    CrawledPage(
                        snapshot_id=snapshot.id,
                        url=url,
                        canonical_url=url,
                        http_status=result.status_code,
                        content_type=content_type,
                        sha256=sha256,
                        robots_status=RobotsStatus.ALLOWED,
                        metadata_json={"note": "non-HTML content; not ingested as a chunked document"},
                    )
                )

            snapshot.page_count = page_count
            await db.commit()

            if progress_callback:
                await progress_callback(page_count, settings.max_pages)

            delay_seconds = max(
                settings.crawl_delay_ms / 1000,
                (robots_crawl_delay(robots_parser, USER_AGENT) or 0),
            )
            if delay_seconds:
                await asyncio.sleep(delay_seconds)

    if snapshot.previous_snapshot_id:
        await apply_diff_against_previous(db, snapshot)

    snapshot.status = JobStatus.COMPLETE
    snapshot.completed_at = datetime.now(timezone.utc)
    await db.commit()


async def apply_diff_against_previous(db: AsyncSession, snapshot: CrawlSnapshot) -> None:
    if not snapshot.previous_snapshot_id:
        return

    old_rows = (
        await db.execute(select(CrawledPage).where(CrawledPage.snapshot_id == snapshot.previous_snapshot_id))
    ).scalars().all()
    new_rows = (
        await db.execute(select(CrawledPage).where(CrawledPage.snapshot_id == snapshot.id))
    ).scalars().all()

    old_snapshots = [PageSnapshot(p.canonical_url, p.sha256, p.title) for p in old_rows if p.sha256]
    new_by_canonical = {p.canonical_url: p for p in new_rows if p.sha256}
    new_snapshots = [PageSnapshot(url, p.sha256, p.title) for url, p in new_by_canonical.items()]

    entries_by_url = {e.canonical_url: e for e in diff_snapshots(old_snapshots, new_snapshots)}

    for canonical_url, page in new_by_canonical.items():
        entry = entries_by_url.get(canonical_url)
        if entry is None:
            continue
        page.changed_from_prior = entry.change_type in ("added", "changed")
        if entry.change_type == "added":
            page.change_summary = "New page since previous snapshot."
        elif entry.change_type == "changed":
            page.change_summary = f"Content changed since previous snapshot (title: {entry.old_title!r} -> {entry.new_title!r})."
        else:
            page.change_summary = None

    await db.commit()
