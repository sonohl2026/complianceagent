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
    },
)

# Task modules must be imported explicitly (not module-name "tasks", so
# Celery's autodiscover_tasks convention doesn't apply) so their @celery_app.task
# decorators register.
from app.workers import analysis_tasks, crawl_tasks, ingestion_tasks, monitoring_tasks, quick_scan_tasks  # noqa: E402,F401
