from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "medtech_compliance_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    beat_schedule={
        # Checks every 30 minutes for ScheduledRecrawl rows whose
        # next_run_at has passed and dispatches them -- the schedules
        # themselves carry their own interval_hours, this just needs to
        # poll often enough that no schedule waits much longer than its own
        # interval. Not every 5 minutes: no scheduled interval is going to
        # be granular enough that 30-minute polling meaningfully delays it,
        # and this runs even when nothing is due.
        "dispatch-due-recrawls": {
            "task": "monitoring.dispatch_due_recrawls",
            "schedule": 1800.0,
        },
        # PFS RVU files only change ~4x/year -- weekly is ample lead time,
        # not trying to catch a same-day correction. refresh_pfs itself is
        # a no-op-on-failure (keeps last-known-good data), so running this
        # often is cheap and safe even if CMS's page structure drifts.
        "refresh-pfs-fee-schedule": {
            "task": "fee_schedule.refresh_pfs",
            "schedule": 7 * 24 * 3600.0,
        },
        # Confirmation-pause runs must not orphan (MVP lockdown Step 3) --
        # the pause itself times out after 30 minutes, so this polls at 1/6th
        # of that so no stale AWAITING_CONFIRMATION run waits much past its
        # own deadline.
        "expire-stale-confirmations": {
            "task": "quick_scan.expire_stale_confirmations",
            "schedule": 300.0,
        },
    },
)

# Task modules must be imported explicitly (not module-name "tasks", so
# Celery's autodiscover_tasks convention doesn't apply) so their @celery_app.task
# decorators register.
from app.workers import crawl_tasks, fee_schedule_tasks, ingestion_tasks, monitoring_tasks, quick_scan_tasks  # noqa: E402,F401
