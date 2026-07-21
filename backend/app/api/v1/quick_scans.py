import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
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
from app.services.llm.cost_estimate import QUICK_SCAN_STAGE_MAX_TOKENS, preflight_credit_check
from app.services.parsing.dispatch import SUPPORTED_EXTENSIONS, parse_document
from app.services.parsing.base import ParsingError
from app.services.parsing.parsers.html_parser import parse_html
from app.services.storage.settings_store import load_runtime_settings
# Imported at module level -- see the comment in api/v1/crawls.py for why.
from app.workers.quick_scan_tasks import quick_scan_override_task, run_quick_scan_task

router = APIRouter()


async def _resolve_source_text_from_url(source_url: str) -> str:
    async with httpx.AsyncClient() as client:
        result = await safe_fetch(client, source_url)
    parsed = parse_html(result.content)
    return parsed.full_text


def _require_ready_settings() -> dict:
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
    return runtime_settings


async def _launch_quick_scan(
    db: AsyncSession,
    project_id: uuid.UUID,
    product_id_str: str | None,
    source_text: str,
    source_url: str | None,
) -> Job:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runtime_settings = _require_ready_settings()
    credit_error = await preflight_credit_check(
        runtime_settings["openrouter_api_key"],
        runtime_settings["openrouter_model"],
        stage_max_tokens=QUICK_SCAN_STAGE_MAX_TOKENS,
    )
    if credit_error:
        raise HTTPException(status_code=402, detail=credit_error)

    if not source_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the given input.")

    product_id = uuid.UUID(product_id_str) if product_id_str else project.default_product_id
    analysis_run = AnalysisRun(
        project_id=project_id,
        product_id=product_id,
        analysis_type="quick_scan",
        status=JobStatus.QUEUED,
        input_snapshot_json={"source_text": source_text, "source_url": source_url},
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


@router.post("/projects/{project_id}/quick-scans", response_model=JobRead, status_code=202)
async def start_quick_scan(
    project_id: uuid.UUID, payload: QuickScanCreateRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    source_text = payload.source_text or await _resolve_source_text_from_url(payload.source_url)
    return await _launch_quick_scan(db, project_id, payload.product_id, source_text, payload.source_url)


@router.post("/projects/{project_id}/quick-scans/upload", response_model=JobRead, status_code=202)
async def start_quick_scan_from_file(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    product_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> Job:
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {extension or '(none)'!r}. Accepted: {', '.join(SUPPORTED_EXTENSIONS)}.",
        )
    content = await file.read()
    try:
        parsed = parse_document(extension, content)
    except ParsingError as exc:
        raise HTTPException(status_code=400, detail=f"Could not read {file.filename}: {exc}") from exc

    return await _launch_quick_scan(db, project_id, product_id, parsed.full_text, None)


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
