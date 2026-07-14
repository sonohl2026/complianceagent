import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.crawl import CrawledPage, CrawlSnapshot
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.project import Project
from app.schemas.crawl import (
    CrawlCreateRequest,
    CrawlDiffEntry,
    CrawlDiffResponse,
    CrawledPageRead,
    CrawlSnapshotRead,
    CrawlSnapshotWithProject,
)
from app.schemas.job import JobRead
from app.services.crawling.crawler import CrawlSettings
from app.services.crawling.diff import PageSnapshot, diff_snapshots, summarize_diff
from app.services.jobs.enqueue import enqueue_job
# Imported at module level (not deferred inside the handler) so a broken
# import in the worker task chain fails loudly at container startup rather
# than silently only on the first crawl request (see enqueue.py docstring).
from app.workers.crawl_tasks import run_crawl_task

router = APIRouter()


@router.post("/projects/{project_id}/crawls", response_model=JobRead, status_code=202)
async def start_crawl(
    project_id: uuid.UUID, payload: CrawlCreateRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    app_settings = get_settings()
    crawl_settings = CrawlSettings(
        start_url=payload.start_url,
        max_pages=payload.max_pages or app_settings.max_crawl_pages,
        max_depth=payload.max_depth if payload.max_depth is not None else app_settings.max_crawl_depth,
        follow_subdomains=payload.follow_subdomains,
        include_pdfs=payload.include_pdfs,
        inclusion_patterns=payload.inclusion_patterns,
        exclusion_patterns=payload.exclusion_patterns,
        crawl_delay_ms=app_settings.crawl_delay_ms,
        render_js=payload.render_js,
    )

    previous_snapshot_id = None
    if payload.rerun_from_previous:
        previous_snapshot_id = await db.scalar(
            select(CrawlSnapshot.id)
            .where(CrawlSnapshot.project_id == project_id, CrawlSnapshot.status == JobStatus.COMPLETE)
            .order_by(CrawlSnapshot.completed_at.desc())
            .limit(1)
        )

    snapshot = CrawlSnapshot(
        project_id=project_id,
        root_url=payload.start_url,
        status=JobStatus.QUEUED,
        crawl_settings_json=crawl_settings.as_dict(),
        previous_snapshot_id=previous_snapshot_id,
    )
    db.add(snapshot)
    await db.flush()

    job = Job(job_type="website_crawl", project_id=project_id, status=JobStatus.QUEUED, related_id=snapshot.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(snapshot)

    await enqueue_job(
        db, job, run_crawl_task, str(job.id), str(snapshot.id), crawl_settings.as_dict(), also_fail=[snapshot]
    )

    return job


@router.get("/projects/{project_id}/crawls", response_model=list[CrawlSnapshotRead])
async def list_project_crawls(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[CrawlSnapshot]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(CrawlSnapshot)
        .where(CrawlSnapshot.project_id == project_id)
        .order_by(CrawlSnapshot.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/crawls", response_model=list[CrawlSnapshotWithProject])
async def list_all_crawls(
    project_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
) -> list[CrawlSnapshotWithProject]:
    query = select(CrawlSnapshot, Project.name).join(Project, CrawlSnapshot.project_id == Project.id)
    if project_id is not None:
        query = query.where(CrawlSnapshot.project_id == project_id)
    query = query.order_by(CrawlSnapshot.created_at.desc())

    rows = (await db.execute(query)).all()
    return [
        CrawlSnapshotWithProject(**CrawlSnapshotRead.model_validate(snap).model_dump(), project_name=project_name)
        for snap, project_name in rows
    ]


@router.get("/crawls/{crawl_id}", response_model=CrawlSnapshotRead)
async def get_crawl(crawl_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CrawlSnapshot:
    snapshot = await db.get(CrawlSnapshot, crawl_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Crawl snapshot not found")
    return snapshot


@router.get("/crawls/{crawl_id}/pages", response_model=list[CrawledPageRead])
async def list_crawl_pages(crawl_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[CrawledPage]:
    snapshot = await db.get(CrawlSnapshot, crawl_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Crawl snapshot not found")
    result = await db.execute(
        select(CrawledPage).where(CrawledPage.snapshot_id == crawl_id).order_by(CrawledPage.created_at)
    )
    return list(result.scalars().all())


@router.post("/crawls/{crawl_id}/cancel", response_model=CrawlSnapshotRead)
async def cancel_crawl(crawl_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CrawlSnapshot:
    snapshot = await db.get(CrawlSnapshot, crawl_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Crawl snapshot not found")
    if snapshot.status in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Crawl is already {snapshot.status.value}")
    # Cooperative cancellation: the running crawl checks this column between
    # each page fetch (app/services/crawling/crawler.py::run_crawl) and stops
    # itself; there is no forced task kill.
    snapshot.status = JobStatus.CANCELLED
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


@router.get("/crawls/{crawl_id}/diff", response_model=CrawlDiffResponse)
async def get_crawl_diff(crawl_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> CrawlDiffResponse:
    snapshot = await db.get(CrawlSnapshot, crawl_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Crawl snapshot not found")

    new_rows = (
        await db.execute(select(CrawledPage).where(CrawledPage.snapshot_id == crawl_id))
    ).scalars().all()
    new_snapshots = [PageSnapshot(p.canonical_url, p.sha256, p.title) for p in new_rows if p.sha256]

    old_snapshots: list[PageSnapshot] = []
    if snapshot.previous_snapshot_id:
        old_rows = (
            await db.execute(
                select(CrawledPage).where(CrawledPage.snapshot_id == snapshot.previous_snapshot_id)
            )
        ).scalars().all()
        old_snapshots = [PageSnapshot(p.canonical_url, p.sha256, p.title) for p in old_rows if p.sha256]

    entries = diff_snapshots(old_snapshots, new_snapshots)
    return CrawlDiffResponse(
        previous_snapshot_id=snapshot.previous_snapshot_id,
        current_snapshot_id=snapshot.id,
        summary=summarize_diff(entries),
        entries=[
            CrawlDiffEntry(
                canonical_url=e.canonical_url,
                change_type=e.change_type,
                old_title=e.old_title,
                new_title=e.new_title,
            )
            for e in entries
        ],
    )
