"""Celery Beat's periodic dispatch of due scheduled recrawls (Milestone 8):
enqueues the same crawling.run_crawl task a manual crawl uses (with
is_scheduled=True so it also runs material-change assessment after
completing -- see app/workers/crawl_tasks.py), then advances next_run_at
immediately so a slow-running crawl can't get double-dispatched on the next
Beat tick.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlSnapshot
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.monitoring import ScheduledRecrawl

logger = logging.getLogger(__name__)


async def dispatch_due_schedules(db: AsyncSession) -> int:
    from app.workers.crawl_tasks import run_crawl_task  # deferred: avoid import cycle at module load

    now = datetime.now(timezone.utc)
    due = (
        await db.execute(
            select(ScheduledRecrawl).where(
                ScheduledRecrawl.is_active.is_(True), ScheduledRecrawl.next_run_at <= now
            )
        )
    ).scalars().all()

    dispatched = 0
    for schedule in due:
        previous_snapshot_id = await db.scalar(
            select(CrawlSnapshot.id)
            .where(CrawlSnapshot.project_id == schedule.project_id, CrawlSnapshot.status == JobStatus.COMPLETE)
            .order_by(CrawlSnapshot.completed_at.desc())
            .limit(1)
        )

        snapshot = CrawlSnapshot(
            project_id=schedule.project_id,
            root_url=schedule.start_url,
            status=JobStatus.QUEUED,
            crawl_settings_json=schedule.crawl_settings_json,
            previous_snapshot_id=previous_snapshot_id,
        )
        db.add(snapshot)
        await db.flush()

        job = Job(
            job_type="scheduled_website_crawl",
            project_id=schedule.project_id,
            status=JobStatus.QUEUED,
            related_id=snapshot.id,
        )
        db.add(job)
        await db.flush()

        # Advance the schedule before attempting to enqueue -- a transient
        # broker failure here shouldn't cause the same schedule to be
        # dispatched again seconds later on the next Beat tick.
        schedule.last_run_at = now
        schedule.next_run_at = now + timedelta(hours=schedule.interval_hours)
        await db.commit()
        await db.refresh(job)
        await db.refresh(snapshot)

        try:
            run_crawl_task.delay(str(job.id), str(snapshot.id), schedule.crawl_settings_json, True)
            dispatched += 1
        except Exception as exc:  # noqa: BLE001 - must not leave an orphaned QUEUED row
            error = f"Failed to enqueue scheduled recrawl: {exc}"
            job.status = JobStatus.FAILED
            job.error_summary = error
            snapshot.status = JobStatus.FAILED
            snapshot.error_summary = error
            await db.commit()
            logger.error(error)

    return dispatched
