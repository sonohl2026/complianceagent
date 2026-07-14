"""Safely enqueue a Celery task after its tracking row(s) are already
committed.

Real incident this fixes: a document-upload/crawl/analysis endpoint commits
a Job (and CrawlSnapshot/AnalysisRun) row as QUEUED, then calls
`task.delay(...)`. If that call itself raises -- a broker connection
problem, or (as actually happened) a `ModuleNotFoundError` surfacing only
when the task module is first imported inside the request -- the row is
left permanently QUEUED with no worker ever picking it up, and the client
saw a raw "Failed to fetch" instead of a clear error. This wraps that call
so a failure is recorded on the row(s) and returned to the client as a
proper error response instead of a silent orphan.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import JobStatus
from app.models.job import Job


async def enqueue_job(db: AsyncSession, job: Job, task, *args, also_fail: list | None = None) -> None:
    try:
        task.delay(*args)
    except Exception as exc:  # noqa: BLE001 - any enqueue failure must not leave an orphaned QUEUED row
        error = f"Failed to enqueue background job: {exc}"
        job.status = JobStatus.FAILED
        job.error_summary = error
        for obj in also_fail or []:
            if hasattr(obj, "status"):
                obj.status = JobStatus.FAILED
            if hasattr(obj, "error_summary"):
                obj.error_summary = error
        await db.commit()
        raise HTTPException(status_code=502, detail=error) from exc
