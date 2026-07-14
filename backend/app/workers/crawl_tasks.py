import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.database import create_worker_engine_and_sessionmaker
from app.models.crawl import CrawlSnapshot
from app.models.enums import JobStatus
from app.models.job import Job
from app.services.crawling.crawler import CrawlSettings, run_crawl
from app.services.storage.settings_store import load_runtime_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="crawling.run_crawl")
def run_crawl_task(job_id: str, snapshot_id: str, settings_dict: dict, is_scheduled: bool = False) -> None:
    asyncio.run(_run_crawl(job_id, snapshot_id, settings_dict, is_scheduled))


async def _run_material_change_assessment(db, snapshot: CrawlSnapshot) -> None:
    # Additive on top of crawling, not core to it: a missing/invalid API key
    # or a classification failure must not fail the crawl itself, since the
    # crawl already succeeded and its results are already good.
    from app.services.llm.base import LLMProviderError, LLMValidationError
    from app.services.llm.openrouter_provider import OpenRouterProvider
    from app.services.monitoring.material_change import assess_material_changes

    settings = load_runtime_settings()
    if not settings.get("openrouter_api_key") or not settings.get("openrouter_model"):
        logger.info("Skipping material-change assessment for snapshot %s: no API key/model configured.", snapshot.id)
        return
    try:
        llm = OpenRouterProvider(api_key=settings.get("openrouter_api_key"))
        alerts = await assess_material_changes(db, llm, settings["openrouter_model"], snapshot)
        if alerts:
            logger.info("Snapshot %s: %d material-change alert(s) raised.", snapshot.id, len(alerts))
    except (LLMProviderError, LLMValidationError) as exc:
        logger.warning("Material-change assessment failed for snapshot %s: %s", snapshot.id, exc)


async def _run_crawl(job_id: str, snapshot_id: str, settings_dict: dict, is_scheduled: bool = False) -> None:
    engine, SessionLocal = create_worker_engine_and_sessionmaker()
    try:
        async with SessionLocal() as db:
            job = await db.get(Job, uuid.UUID(job_id))
            snapshot = await db.get(CrawlSnapshot, uuid.UUID(snapshot_id))
            if job is None or snapshot is None:
                return

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.current_stage = "crawling"
            await db.commit()

            settings = CrawlSettings(**settings_dict)

            async def progress(page_count: int, max_pages: int) -> None:
                job.progress_percent = min(99, int(100 * page_count / max(max_pages, 1)))
                job.current_stage = f"crawling ({page_count}/{max_pages} pages)"
                await db.commit()

            try:
                await run_crawl(db, snapshot, settings, progress_callback=progress)
                await db.refresh(snapshot)
                if snapshot.status == JobStatus.CANCELLED:
                    job.status = JobStatus.CANCELLED
                    job.current_stage = "cancelled"
                else:
                    job.status = JobStatus.COMPLETE
                    job.progress_percent = 100
                    job.current_stage = "complete"
                    if is_scheduled:
                        job.current_stage = "assessing material changes"
                        await db.commit()
                        await _run_material_change_assessment(db, snapshot)
                        job.current_stage = "complete"
                job.related_id = snapshot.id
            except Exception as exc:  # noqa: BLE001 - surface crawl failures to the Job + CrawlSnapshot records
                job.status = JobStatus.FAILED
                job.error_summary = str(exc)
                snapshot.status = JobStatus.FAILED
                snapshot.error_summary = str(exc)
            finally:
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        await engine.dispose()
