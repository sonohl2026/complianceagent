import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import AnalysisRun
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.project import Project
from app.schemas.job import JobRead
from app.schemas.quick_scan import OverrideRequest, QuickScanCreateRequest
from app.services.crawling.fetch import safe_fetch
from app.services.jobs.enqueue import enqueue_job
from app.services.llm.cost_estimate import preflight_credit_check
from app.services.parsing.parsers.html_parser import parse_html
from app.services.storage.settings_store import load_runtime_settings
# Imported at module level -- see the comment in api/v1/crawls.py for why.
from app.workers.quick_scan_tasks import quick_scan_override_task, run_quick_scan_task

router = APIRouter()


async def _resolve_source_text(payload: QuickScanCreateRequest) -> str:
    if payload.source_text:
        return payload.source_text
    async with httpx.AsyncClient() as client:
        result = await safe_fetch(client, payload.source_url)
    parsed = parse_html(result.content)
    return parsed.full_text


@router.post("/projects/{project_id}/quick-scans", response_model=JobRead, status_code=202)
async def start_quick_scan(
    project_id: uuid.UUID, payload: QuickScanCreateRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runtime_settings = load_runtime_settings()
    if not runtime_settings.get("openrouter_api_key"):
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter API key configured. Add one in Settings before running a quick scan.",
        )
    if not runtime_settings.get("openrouter_model"):
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter model configured. Set an exact model slug in Settings before running a quick scan.",
        )

    credit_error = await preflight_credit_check(
        runtime_settings["openrouter_api_key"], runtime_settings["openrouter_model"]
    )
    if credit_error:
        raise HTTPException(status_code=402, detail=credit_error)

    source_text = await _resolve_source_text(payload)

    product_id = uuid.UUID(payload.product_id) if payload.product_id else project.default_product_id
    analysis_run = AnalysisRun(
        project_id=project_id,
        product_id=product_id,
        analysis_type="quick_scan",
        status=JobStatus.QUEUED,
        input_snapshot_json={"source_text": source_text, "source_url": payload.source_url},
    )
    db.add(analysis_run)
    await db.flush()

    job = Job(job_type="quick_scan", project_id=project_id, status=JobStatus.QUEUED, related_id=analysis_run.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(analysis_run)

    await enqueue_job(db, job, run_quick_scan_task, str(job.id), str(analysis_run.id), also_fail=[analysis_run])

    return job


@router.post("/quick-scans/{analysis_id}/override", response_model=JobRead, status_code=202)
async def override_quick_scan(
    analysis_id: uuid.UUID, payload: OverrideRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None or analysis_run.analysis_type != "quick_scan":
        raise HTTPException(status_code=404, detail="Quick scan not found")
    if analysis_run.status != JobStatus.COMPLETE:
        raise HTTPException(status_code=400, detail="Can only override a completed quick scan")

    now = datetime.now(timezone.utc).isoformat()
    updated_overrides = dict(analysis_run.overrides_json)
    for item in payload.overrides:
        updated_overrides[f"{item.target}.{item.key}"] = {"value": item.value, "edited_at": now}
    analysis_run.overrides_json = updated_overrides
    analysis_run.status = JobStatus.QUEUED
    db.add(analysis_run)
    await db.flush()

    job = Job(
        job_type="quick_scan_override", project_id=analysis_run.project_id,
        status=JobStatus.QUEUED, related_id=analysis_run.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(analysis_run)

    await enqueue_job(db, job, quick_scan_override_task, str(job.id), str(analysis_run.id), also_fail=[analysis_run])

    return job
