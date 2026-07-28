import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import create_worker_engine_and_sessionmaker
from app.models.analysis import AnalysisRun
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.product import Product
from app.services.llm.base import LLMProviderError, LLMValidationError
from app.services.llm.openrouter_provider import OpenRouterProvider
from app.services.quick_scan.pipeline import (
    run_quick_scan,
    run_quick_scan_identity_resolution,
    run_quick_scan_override,
)
from app.services.quick_scan.stage3_synthesis import QuickScanSynthesisError
from app.services.storage.settings_store import load_runtime_settings
from app.workers.celery_app import celery_app

# Mirrors app/workers/analysis_tasks.py's status-mapping shape exactly, for
# the new quick_scan analysis_type rather than FULL_COMPLIANCE_ANALYSIS.
_FAILURE_EXCEPTIONS = (LLMProviderError, LLMValidationError, QuickScanSynthesisError)


@celery_app.task(name="quick_scan.run")
def run_quick_scan_task(job_id: str, analysis_run_id: str) -> None:
    asyncio.run(_run(job_id, analysis_run_id, override=False))


@celery_app.task(name="quick_scan.override")
def quick_scan_override_task(job_id: str, analysis_run_id: str) -> None:
    asyncio.run(_run(job_id, analysis_run_id, override=True))


@celery_app.task(name="quick_scan.resolve_identity")
def run_quick_scan_identity_resolution_task(job_id: str, analysis_run_id: str, product_name: str) -> None:
    asyncio.run(_run_identity_resolution(job_id, analysis_run_id, product_name))


async def _run_identity_resolution(job_id: str, analysis_run_id: str, product_name: str) -> None:
    """Name-only submission's first half (MVP lockdown Step 3): mirrors _run's
    RUNNING->terminal-state guarantee exactly, but the success terminal state
    is AWAITING_CONFIRMATION rather than COMPLETE -- the pipeline genuinely
    isn't done, it's paused for the user. Job.status stays COMPLETE on
    success either way: the *job* (this queued unit of work) really did run
    to completion, it's the AnalysisRun's own status that carries the
    paused-for-confirmation meaning (Job's status column is a separate
    Postgres enum that was deliberately not widened for this -- see
    migration 0012 -- since nothing needs Job itself to express this state)."""
    engine, SessionLocal = create_worker_engine_and_sessionmaker()
    try:
        async with SessionLocal() as db:
            job = await db.get(Job, uuid.UUID(job_id))
            analysis_run = await db.get(AnalysisRun, uuid.UUID(analysis_run_id))
            if job is None or analysis_run is None:
                return

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            analysis_run.status = JobStatus.RUNNING
            analysis_run.started_at = datetime.now(timezone.utc)
            await db.commit()

            runtime_settings = load_runtime_settings()
            model = runtime_settings.get("openrouter_model") or ""

            try:
                llm = OpenRouterProvider(
                    api_key=runtime_settings.get("openrouter_api_key"),
                    prompt_caching=runtime_settings.get("openrouter_prompt_caching", True),
                )
                identity_found = await run_quick_scan_identity_resolution(db, analysis_run, llm, model, product_name)
                job.status = JobStatus.COMPLETE
                job.progress_percent = 100
                job.current_stage = "awaiting_confirmation"
                analysis_run.status = JobStatus.AWAITING_CONFIRMATION
                has_candidate_site = "candidate_site" in analysis_run.retrieval_bundle_json
                if not identity_found and not has_candidate_site:
                    analysis_run.error_summary = (
                        "No FDA/coverage record found under that name, and no candidate site turned up "
                        "either. Correct the name or attach a document."
                    )
            except _FAILURE_EXCEPTIONS as exc:
                job.status = JobStatus.FAILED
                job.error_summary = str(exc)
                analysis_run.status = JobStatus.FAILED
                analysis_run.error_summary = str(exc)
            except Exception as exc:  # noqa: BLE001 - surface any unexpected pipeline failure
                job.status = JobStatus.FAILED
                job.error_summary = f"Unexpected error: {exc}"
                analysis_run.status = JobStatus.FAILED
                analysis_run.error_summary = f"Unexpected error: {exc}"
            finally:
                job.completed_at = datetime.now(timezone.utc)
                # AWAITING_CONFIRMATION is a pause, not a terminal state --
                # completed_at stays unset so it isn't mistaken for a
                # finished run (the expiry sweep or the confirm flow sets it
                # when the run actually reaches a terminal status).
                if analysis_run.status != JobStatus.AWAITING_CONFIRMATION:
                    analysis_run.completed_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        await engine.dispose()


async def _run(job_id: str, analysis_run_id: str, *, override: bool) -> None:
    engine, SessionLocal = create_worker_engine_and_sessionmaker()
    try:
        async with SessionLocal() as db:
            job = await db.get(Job, uuid.UUID(job_id))
            analysis_run = await db.get(AnalysisRun, uuid.UUID(analysis_run_id))
            if job is None or analysis_run is None:
                return

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            analysis_run.status = JobStatus.RUNNING
            analysis_run.started_at = datetime.now(timezone.utc)
            await db.commit()

            runtime_settings = load_runtime_settings()
            model = runtime_settings.get("openrouter_model") or ""

            try:
                llm = OpenRouterProvider(
                    api_key=runtime_settings.get("openrouter_api_key"),
                    prompt_caching=runtime_settings.get("openrouter_prompt_caching", True),
                )
                if override:
                    await run_quick_scan_override(db, analysis_run, llm, model)
                else:
                    source_text = analysis_run.input_snapshot_json.get("source_text", "")
                    name_hint = analysis_run.input_snapshot_json.get("product_name_hint")
                    await run_quick_scan(db, analysis_run, llm, model, source_text, product_name_hint=name_hint)
                job.status = JobStatus.COMPLETE
                job.progress_percent = 100
                job.current_stage = "complete"
                analysis_run.status = JobStatus.COMPLETE
                await _sync_product_name_from_result(db, analysis_run)
            except _FAILURE_EXCEPTIONS as exc:
                job.status = JobStatus.FAILED
                job.error_summary = str(exc)
                analysis_run.status = JobStatus.FAILED
                analysis_run.error_summary = str(exc)
            except Exception as exc:  # noqa: BLE001 - surface any unexpected pipeline failure
                job.status = JobStatus.FAILED
                job.error_summary = f"Unexpected error: {exc}"
                analysis_run.status = JobStatus.FAILED
                analysis_run.error_summary = f"Unexpected error: {exc}"
            finally:
                job.completed_at = datetime.now(timezone.utc)
                analysis_run.completed_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        await engine.dispose()


async def _sync_product_name_from_result(db: AsyncSession, analysis_run: AnalysisRun) -> None:
    """The Products list is the app's home page now (MVP lockdown Step 1) --
    it needs a real name per product, but a material-only submission (no
    typed name) doesn't know one until Stage 1 resolves it. Keeps the
    Product row's name in step with whatever identity Stage 3 actually
    settled on, every time a run completes -- unless the user has manually
    renamed it (products.py::rename_product sets name_manually_set), in
    which case that rename is a deliberate choice this must not undo."""
    if analysis_run.product_id is None:
        return
    resolved_name = (analysis_run.quick_scan_result_json.get("product") or {}).get("name")
    if not resolved_name:
        return
    product = await db.get(Product, analysis_run.product_id)
    if product is not None and not product.name_manually_set:
        product.name = resolved_name


_CONFIRMATION_TIMEOUT_MINUTES = 30


@celery_app.task(name="quick_scan.expire_stale_confirmations")
def expire_stale_confirmations_task() -> None:
    asyncio.run(_expire_stale_confirmations())


async def _expire_stale_confirmations() -> None:
    """Confirmation-pause runs must not orphan (MVP lockdown Step 3): a run
    stuck in AWAITING_CONFIRMATION because the user never came back gets
    swept to a terminal FAILED state, same as the crashed-run guarantee
    already verified for the main pipeline -- this is the same guarantee
    extended to a state that pauses for a human instead of a model call."""
    from sqlalchemy import select

    engine, SessionLocal = create_worker_engine_and_sessionmaker()
    try:
        async with SessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=_CONFIRMATION_TIMEOUT_MINUTES)
            result = await db.execute(
                select(AnalysisRun).where(
                    AnalysisRun.status == JobStatus.AWAITING_CONFIRMATION,
                    AnalysisRun.started_at < cutoff,
                )
            )
            for analysis_run in result.scalars().all():
                analysis_run.status = JobStatus.FAILED
                analysis_run.error_summary = (
                    f"Confirmation timed out after {_CONFIRMATION_TIMEOUT_MINUTES} minutes without a response."
                )
                analysis_run.completed_at = datetime.now(timezone.utc)
            await db.commit()
    finally:
        await engine.dispose()
