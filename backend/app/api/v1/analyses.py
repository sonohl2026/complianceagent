import dataclasses
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.analysis import AnalysisRun, Finding
from app.models.coding import CodingCandidate
from app.models.enums import JobStatus
from app.models.job import Job
from app.models.product import Product
from app.models.project import Project
from app.schemas.analysis import AnalysisCreateRequest, AnalysisRunRead, CodingCandidateRead, FindingRead
from app.schemas.dashboard import RecentAnalysisRow
from app.schemas.job import JobRead
from app.services.jobs.enqueue import enqueue_job
from app.services.llm.cost_estimate import preflight_credit_check
from app.services.reporting.data import gather_report_data
from app.services.reporting.markdown_report import build_markdown_report
from app.services.storage.settings_store import load_runtime_settings
# Imported at module level -- see the comment in api/v1/crawls.py for why.
from app.workers.analysis_tasks import run_analysis_task

router = APIRouter()


@router.post("/projects/{project_id}/analyses", response_model=JobRead, status_code=202)
async def start_analysis(
    project_id: uuid.UUID, payload: AnalysisCreateRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    runtime_settings = load_runtime_settings()
    if not runtime_settings.get("openrouter_api_key"):
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter API key configured. Add one in Settings before running an analysis.",
        )
    if not runtime_settings.get("openrouter_model"):
        raise HTTPException(
            status_code=400,
            detail="No OpenRouter model configured. Set an exact model slug in Settings before running an analysis.",
        )

    credit_error = await preflight_credit_check(
        runtime_settings["openrouter_api_key"], runtime_settings["openrouter_model"]
    )
    if credit_error:
        raise HTTPException(status_code=402, detail=credit_error)

    analysis_run = AnalysisRun(
        project_id=project_id,
        product_id=payload.product_id or project.default_product_id,
        analysis_type=payload.analysis_type,
        status=JobStatus.QUEUED,
    )
    db.add(analysis_run)
    await db.flush()

    job = Job(job_type="compliance_analysis", project_id=project_id, status=JobStatus.QUEUED, related_id=analysis_run.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await db.refresh(analysis_run)

    await enqueue_job(db, job, run_analysis_task, str(job.id), str(analysis_run.id), also_fail=[analysis_run])

    return job


@router.get("/projects/{project_id}/analyses", response_model=list[AnalysisRunRead])
async def list_project_analyses(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[AnalysisRun]:
    result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.project_id == project_id).order_by(AnalysisRun.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/analyses", response_model=list[RecentAnalysisRow])
async def list_all_analyses(
    project_id: uuid.UUID | None = None, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> list[RecentAnalysisRow]:
    query = (
        select(AnalysisRun, Project.name, Product.name)
        .join(Project, AnalysisRun.project_id == Project.id)
        .outerjoin(Product, AnalysisRun.product_id == Product.id)
    )
    if project_id is not None:
        query = query.where(AnalysisRun.project_id == project_id)
    query = query.order_by(AnalysisRun.created_at.desc()).limit(limit)

    rows = (await db.execute(query)).all()
    return [
        RecentAnalysisRow(
            id=run.id,
            project_id=run.project_id,
            project_name=project_name,
            product_name=product_name,
            status=run.status.value,
            overall_verdict=run.overall_verdict.value if run.overall_verdict else None,
            overall_risk=run.overall_risk.value if run.overall_risk else None,
            readiness_score=run.readiness_score,
            created_at=run.created_at,
        )
        for run, project_name, product_name in rows
    ]


@router.get("/analyses/{analysis_id}", response_model=AnalysisRunRead)
async def get_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AnalysisRun:
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return analysis_run


@router.post("/analyses/{analysis_id}/cancel", response_model=AnalysisRunRead)
async def cancel_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> AnalysisRun:
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    if analysis_run.status in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Analysis is already {analysis_run.status.value}")
    # Cooperative cancellation: app/services/analysis/pipeline.py checks this
    # column between stages and stops itself; no forced task kill.
    analysis_run.status = JobStatus.CANCELLED
    await db.commit()
    await db.refresh(analysis_run)
    return analysis_run


@router.post("/analyses/{analysis_id}/retry", response_model=JobRead, status_code=202)
async def retry_analysis(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Job:
    previous = await db.get(AnalysisRun, analysis_id)
    if previous is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    if previous.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Only a failed or cancelled analysis can be retried")

    runtime_settings = load_runtime_settings()
    if not runtime_settings.get("openrouter_api_key") or not runtime_settings.get("openrouter_model"):
        raise HTTPException(status_code=400, detail="OpenRouter key/model must be configured in Settings")

    new_run = AnalysisRun(
        project_id=previous.project_id,
        product_id=previous.product_id,
        analysis_type=previous.analysis_type,
        status=JobStatus.QUEUED,
    )
    db.add(new_run)
    await db.flush()

    job = Job(job_type="compliance_analysis", project_id=previous.project_id, status=JobStatus.QUEUED, related_id=new_run.id)
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await enqueue_job(db, job, run_analysis_task, str(job.id), str(new_run.id), also_fail=[new_run])

    return job


@router.get("/analyses/{analysis_id}/findings", response_model=list[FindingRead])
async def list_findings(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[Finding]:
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    result = await db.execute(
        select(Finding)
        .options(selectinload(Finding.citations))
        .where(Finding.analysis_run_id == analysis_id)
        .order_by(Finding.priority.nulls_last(), Finding.created_at)
    )
    return list(result.scalars().all())


@router.get("/analyses/{analysis_id}/coding-candidates", response_model=list[CodingCandidateRead])
async def list_coding_candidates(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[CodingCandidate]:
    analysis_run = await db.get(AnalysisRun, analysis_id)
    if analysis_run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    result = await db.execute(
        select(CodingCandidate)
        .options(selectinload(CodingCandidate.requirements))
        .where(CodingCandidate.analysis_run_id == analysis_id)
    )
    return list(result.scalars().all())


def _validate_mode(mode: str) -> str:
    if mode not in ("condensed", "extended"):
        raise HTTPException(status_code=422, detail="mode must be 'condensed' or 'extended'")
    return mode


@router.get("/analyses/{analysis_id}/export.md")
async def export_markdown(
    analysis_id: uuid.UUID, mode: str = "condensed", db: AsyncSession = Depends(get_db)
) -> Response:
    mode = _validate_mode(mode)
    data = await gather_report_data(db, analysis_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    markdown = build_markdown_report(data, mode=mode)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="analysis-{analysis_id}-{mode}.md"'},
    )


@router.get("/analyses/{analysis_id}/export.json")
async def export_json(analysis_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    data = await gather_report_data(db, analysis_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return dataclasses.asdict(data)


@router.get("/analyses/{analysis_id}/export.pdf")
async def export_pdf(
    analysis_id: uuid.UUID, mode: str = "condensed", db: AsyncSession = Depends(get_db)
) -> Response:
    mode = _validate_mode(mode)
    data = await gather_report_data(db, analysis_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    from app.services.reporting.pdf_report import build_pdf_report

    try:
        pdf_bytes = build_pdf_report(data, mode=mode)
    except Exception as exc:  # noqa: BLE001 - surface PDF rendering failures clearly rather than a bare 500
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="analysis-{analysis_id}-{mode}.pdf"'},
    )
