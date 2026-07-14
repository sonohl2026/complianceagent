import asyncio
import uuid
from datetime import datetime, timezone

from app.database import create_worker_engine_and_sessionmaker
from app.models.analysis import AnalysisRun
from app.models.enums import JobStatus
from app.models.job import Job
from app.services.llm.base import LLMProviderError, LLMValidationError
from app.services.llm.openrouter_provider import OpenRouterProvider
from app.services.analysis.pipeline import AnalysisCancelled, run_analysis
from app.services.storage.settings_store import load_runtime_settings
from app.workers.celery_app import celery_app


@celery_app.task(name="analysis.run")
def run_analysis_task(job_id: str, analysis_run_id: str) -> None:
    asyncio.run(_run_analysis(job_id, analysis_run_id))


async def _run_analysis(job_id: str, analysis_run_id: str) -> None:
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
            await db.commit()

            runtime_settings = load_runtime_settings()
            model = runtime_settings.get("openrouter_model") or ""

            try:
                llm = OpenRouterProvider(api_key=runtime_settings.get("openrouter_api_key"))
                await run_analysis(db, analysis_run, llm, model)
                job.status = JobStatus.COMPLETE
                job.progress_percent = 100
                job.current_stage = "complete"
                analysis_run.status = JobStatus.COMPLETE
            except AnalysisCancelled:
                job.status = JobStatus.CANCELLED
                job.current_stage = "cancelled"
                # analysis_run.status is already CANCELLED -- that's what triggered this exception.
            except (LLMProviderError, LLMValidationError) as exc:
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
