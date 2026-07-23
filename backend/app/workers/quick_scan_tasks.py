import asyncio
import uuid
from datetime import datetime, timezone

from app.database import create_worker_engine_and_sessionmaker
from app.models.analysis import AnalysisRun
from app.models.enums import JobStatus
from app.models.job import Job
from app.services.llm.base import LLMProviderError, LLMValidationError
from app.services.llm.openrouter_provider import OpenRouterProvider
from app.services.quick_scan.pipeline import run_quick_scan, run_quick_scan_override
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
                    await run_quick_scan(db, analysis_run, llm, model, source_text)
                job.status = JobStatus.COMPLETE
                job.progress_percent = 100
                job.current_stage = "complete"
                analysis_run.status = JobStatus.COMPLETE
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
