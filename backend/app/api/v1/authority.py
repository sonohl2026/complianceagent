from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import AuthorityLevel, CollectionType, ConfidentialityLevel, JobStatus
from app.models.job import Job
from app.models.source_document import SourceDocument
from app.schemas.document import SourceDocumentRead, _require_http_scheme
from app.schemas.job import JobRead
from app.services.jobs.enqueue import enqueue_job
from app.services.storage.file_storage import get_storage
# Imported at module level -- see the comment in api/v1/crawls.py for why.
from app.workers.ingestion_tasks import process_upload_task

router = APIRouter()


@router.post("/authority/documents", response_model=JobRead, status_code=202)
async def upload_authority_document(
    file: UploadFile = File(...),
    authority_level: AuthorityLevel = Form(...),
    title: str | None = Form(None),
    issuer: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    source_type: str | None = Form(None),
    url: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> Job:
    try:
        url = _require_http_scheme(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    content = await file.read()
    storage = get_storage()
    holding_path = storage.save_bytes("uploads", content, suffix="-authority")

    job = Job(job_type="authority_ingestion", status=JobStatus.QUEUED, current_stage="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await enqueue_job(
        db,
        job,
        process_upload_task,
        str(job.id),
        "",  # authority documents are not project-scoped
        file.filename or "upload",
        holding_path,
        CollectionType.AUTHORITY.value,
        ConfidentialityLevel.PUBLIC.value,
        title,
        issuer,
        jurisdiction,
        authority_level.value,
        source_type,
        url,
    )
    return job


@router.get("/authority/documents", response_model=list[SourceDocumentRead])
async def list_authority_documents(db: AsyncSession = Depends(get_db)) -> list[SourceDocument]:
    result = await db.execute(
        select(SourceDocument)
        .where(SourceDocument.collection_type == CollectionType.AUTHORITY)
        .order_by(SourceDocument.created_at.desc())
    )
    return list(result.scalars().all())
