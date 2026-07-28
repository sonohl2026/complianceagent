import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import AnalysisRun
from app.models.company import Company
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.product import Product
from app.schemas.job import JobRead
from app.schemas.quick_scan import ConfirmSiteRequest, OverrideRequest
from app.services.crawling.fetch import safe_fetch
from app.services.jobs.enqueue import enqueue_job
from app.services.llm.cost_estimate import preflight_credit_check
from app.services.parsing.dispatch import SUPPORTED_EXTENSIONS, parse_document
from app.services.parsing.base import ParsingError
from app.services.parsing.parsers.html_parser import parse_html
from app.services.storage.settings_store import load_runtime_settings
# Imported at module level -- see the comment in api/v1/crawls.py for why.
from app.workers.quick_scan_tasks import (
    quick_scan_override_task,
    run_quick_scan_identity_resolution_task,
    run_quick_scan_task,
)

router = APIRouter()

_DEFAULT_COMPANY_NAME = "My Products"


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


async def _get_or_create_default_company(db: AsyncSession) -> Company:
    # MVP lockdown Step 1: company selection is part of the scrapped project
    # hierarchy -- the composer never asks for one. A single implicit
    # company holds every product in this single-tenant local deployment.
    result = await db.execute(select(Company).where(Company.name == _DEFAULT_COMPANY_NAME).limit(1))
    company = result.scalars().first()
    if company is not None:
        return company
    company = Company(name=_DEFAULT_COMPANY_NAME)
    db.add(company)
    await db.flush()
    return company


def _fair_share_merge(texts: list[str], max_chars: int) -> str:
    """Multi-file/link merge for Stage 1's ~8k-token cap: naive concatenation
    truncates from the end, so a single large source can silently push every
    other source out entirely. Each source gets an equal share of the
    budget up front instead, so every attached document/link is represented
    in what Stage 1 actually sees."""
    if not texts:
        return ""
    per_source_budget = max(max_chars // len(texts), 1)
    return "\n\n---\n\n".join(text[:per_source_budget] for text in texts)


_MAX_MERGED_CHARS = 8000 * 4  # matches stage1_extraction.py's own cap; this is a pre-truncation courtesy, not a second cap


async def _gather_source_texts(files: list[UploadFile], source_urls: list[str]) -> list[str]:
    texts: list[str] = []
    for file in files:
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
        texts.append(parsed.full_text)

    for url in source_urls:
        if not url.strip():
            continue
        texts.append(await _resolve_source_text_from_url(url.strip()))

    return texts


@router.post("/quick-scans", response_model=JobRead, status_code=202)
async def start_quick_scan(
    product_name: str = Form(""),
    source_urls: list[str] = Form(default=[]),
    files: list[UploadFile] = File(default=[]),
    product_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> Job:
    """The single entry point (MVP lockdown Step 2): any mix of files, links,
    and/or a typed name. Behavior branches on what's actually present --
    material (files/links) always drives the standard extract-from-text
    flow; a bare name skips straight to the name-only identity-confirmation
    flow (Step 3); both together let the name seed identity while the
    material still feeds evidence.

    product_id, when given, re-runs against an existing product (a fresh
    AnalysisRun under it) instead of creating a new one -- the Products
    list's "Re-run" action uses this so re-analyzing a device doesn't leave
    a duplicate product behind."""
    name = product_name.strip()
    source_texts = await _gather_source_texts(files, source_urls)
    has_material = any(text.strip() for text in source_texts)

    if not has_material and not name:
        raise HTTPException(
            status_code=400,
            detail="Provide at least a product name, a link, or a document.",
        )

    runtime_settings = _require_ready_settings()
    credit_error = await preflight_credit_check(
        runtime_settings["openrouter_api_key"], runtime_settings["openrouter_model"]
    )
    if credit_error:
        raise HTTPException(status_code=402, detail=credit_error)

    if product_id:
        product = await db.get(Product, uuid.UUID(product_id))
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
    else:
        company = await _get_or_create_default_company(db)
        product = Product(company_id=company.id, name=name or "Untitled product")
        db.add(product)
        await db.flush()

    if has_material:
        source_text = _fair_share_merge(source_texts, _MAX_MERGED_CHARS)
        analysis_run = AnalysisRun(
            product_id=product.id,
            analysis_type="quick_scan",
            status=JobStatus.QUEUED,
            input_snapshot_json={
                "source_text": source_text,
                "source_url": source_urls[0] if source_urls else None,
                "product_name_hint": name or None,
            },
        )
        db.add(analysis_run)
        await db.flush()
        job = Job(job_type="quick_scan", status=JobStatus.QUEUED, related_id=analysis_run.id)
        db.add(job)
        await db.commit()
        await db.refresh(job)
        await db.refresh(analysis_run)
        await enqueue_job(db, job, run_quick_scan_task, str(job.id), str(analysis_run.id), also_fail=[analysis_run])
        return job

    # Name-only: skip Stage 1 entirely, pause at AWAITING_CONFIRMATION after retrieval.
    analysis_run = AnalysisRun(
        product_id=product.id,
        analysis_type="quick_scan",
        status=JobStatus.QUEUED,
        input_snapshot_json={"source_text": None, "source_url": None, "product_name_hint": name},
    )
    db.add(analysis_run)
    await db.flush()
    job = Job(job_type="quick_scan_identity_resolution", status=JobStatus.QUEUED, related_id=analysis_run.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(analysis_run)
    await enqueue_job(
        db, job, run_quick_scan_identity_resolution_task, str(job.id), str(analysis_run.id), name,
        also_fail=[analysis_run],
    )
    return job


@router.post("/quick-scans/{analysis_id}/override", response_model=JobRead, status_code=202)
async def override_quick_scan(
    analysis_id: uuid.UUID, payload: OverrideRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    """Also doubles as the name-only confirmation endpoint (MVP lockdown
    Step 3): confirming with no edits is just an empty overrides list;
    confirming after an edit reuses the exact same ProductIdentityEdit path
    a completed run's override already used. Either way this is what moves
    an AWAITING_CONFIRMATION run on to Stage 3 and completion."""
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None or analysis_run.analysis_type != "quick_scan":
        raise HTTPException(status_code=404, detail="Quick scan not found")
    if analysis_run.status not in (JobStatus.COMPLETE, JobStatus.AWAITING_CONFIRMATION):
        raise HTTPException(
            status_code=400, detail="Can only override a completed or awaiting-confirmation quick scan"
        )

    now = datetime.now(timezone.utc).isoformat()
    updated_overrides = dict(analysis_run.overrides_json)
    for item in payload.overrides:
        updated_overrides[f"{item.target}.{item.key}"] = {"value": item.value, "edited_at": now}
    analysis_run.overrides_json = updated_overrides
    analysis_run.status = JobStatus.QUEUED
    db.add(analysis_run)
    await db.flush()

    job = Job(job_type="quick_scan_override", status=JobStatus.QUEUED, related_id=analysis_run.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(analysis_run)

    await enqueue_job(db, job, quick_scan_override_task, str(job.id), str(analysis_run.id), also_fail=[analysis_run])

    return job


@router.post("/quick-scans/{analysis_id}/confirm-site", response_model=JobRead, status_code=202)
async def confirm_candidate_site(
    analysis_id: uuid.UUID, payload: ConfirmSiteRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    """Two callers, same mechanism: (a) confirms the web-search candidate
    proposed after a name-only submission's zero-hit
    (pipeline.py::_find_candidate_site), or (b) a link a user supplies
    directly via ProductIdentityEdit to correct an identity they believe is
    wrong -- for a completed run, not just an awaiting-confirmation one.
    Either way this is functionally identical to a name+link submission --
    the URL is fetched and run through the standard extract-then-retrieve-
    then-synthesize flow, straight through to completion (one confirmation,
    not two: the user already confirmed the site/link itself)."""
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None or analysis_run.analysis_type != "quick_scan":
        raise HTTPException(status_code=404, detail="Quick scan not found")
    was_complete = analysis_run.status == JobStatus.COMPLETE
    if not was_complete and analysis_run.status != JobStatus.AWAITING_CONFIRMATION:
        raise HTTPException(
            status_code=400, detail="Can only confirm a site on a completed or awaiting-confirmation quick scan"
        )

    source_text = await _resolve_source_text_from_url(payload.url)
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from that site.")

    name_hint = (
        payload.product_name.strip()
        if payload.product_name and payload.product_name.strip()
        else analysis_run.input_snapshot_json.get("product_name_hint")
    )
    analysis_run.input_snapshot_json = {
        "source_text": source_text, "source_url": payload.url, "product_name_hint": name_hint,
    }
    analysis_run.status = JobStatus.QUEUED
    analysis_run.error_summary = None
    if was_complete:
        analysis_run.revision += 1
    db.add(analysis_run)
    await db.flush()

    job = Job(job_type="quick_scan", status=JobStatus.QUEUED, related_id=analysis_run.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(analysis_run)

    await enqueue_job(db, job, run_quick_scan_task, str(job.id), str(analysis_run.id), also_fail=[analysis_run])

    return job
