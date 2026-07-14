import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import CollectionType, ConfidentialityLevel, JobStatus
from app.models.job import Job
from app.models.project import Project
from app.models.source_chunk import SourceChunk
from app.models.source_document import SourceDocument
from app.schemas.document import (
    SourceChunkRead,
    SourceDocumentMetadataUpdate,
    SourceDocumentRead,
    SourceDocumentWithProject,
)
from app.schemas.job import JobRead
from app.services.jobs.enqueue import enqueue_job
from app.services.storage.file_storage import get_storage
# Imported at module level -- see the comment in api/v1/crawls.py for why.
from app.workers.ingestion_tasks import process_upload_task

router = APIRouter()


@router.post("/projects/{project_id}/documents", response_model=JobRead, status_code=202)
async def upload_document(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    collection_type: CollectionType = Form(CollectionType.COMPANY),
    confidentiality_level: ConfidentialityLevel = Form(ConfidentialityLevel.INTERNAL),
    title: str | None = Form(None),
    issuer: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> Job:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    content = await file.read()
    storage = get_storage()
    holding_path = storage.save_bytes("uploads", content, suffix="-incoming")

    job = Job(
        job_type="document_ingestion",
        project_id=project_id,
        status=JobStatus.QUEUED,
        current_stage="queued",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await enqueue_job(
        db,
        job,
        process_upload_task,
        str(job.id),
        str(project_id),
        file.filename or "upload",
        holding_path,
        collection_type.value,
        confidentiality_level.value,
        title,
        issuer,
        jurisdiction,
    )

    return job


@router.get("/projects/{project_id}/documents", response_model=list[SourceDocumentRead])
async def list_project_documents(
    project_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[SourceDocument]:
    result = await db.execute(
        select(SourceDocument)
        .where(SourceDocument.project_id == project_id)
        .order_by(SourceDocument.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/documents", response_model=list[SourceDocumentWithProject])
async def list_all_documents(
    project_id: uuid.UUID | None = None,
    collection_type: CollectionType | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[SourceDocumentWithProject]:
    # AUTHORITY documents are shared (project_id IS NULL), hence the outer
    # join -- they have no project to name.
    query = select(SourceDocument, Project.name).outerjoin(Project, SourceDocument.project_id == Project.id)
    if project_id is not None:
        query = query.where(SourceDocument.project_id == project_id)
    if collection_type is not None:
        query = query.where(SourceDocument.collection_type == collection_type)
    query = query.order_by(SourceDocument.created_at.desc())

    rows = (await db.execute(query)).all()
    return [
        SourceDocumentWithProject(**SourceDocumentRead.model_validate(doc).model_dump(), project_name=project_name)
        for doc, project_name in rows
    ]


@router.get("/documents/{document_id}", response_model=SourceDocumentRead)
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> SourceDocument:
    document = await db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents/{document_id}/chunks", response_model=list[SourceChunkRead])
async def list_document_chunks(
    document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> list[SourceChunk]:
    result = await db.execute(
        select(SourceChunk)
        .where(SourceChunk.document_id == document_id)
        .order_by(SourceChunk.chunk_index)
    )
    return list(result.scalars().all())


@router.put("/documents/{document_id}", response_model=SourceDocumentRead)
async def update_document_metadata(
    document_id: uuid.UUID,
    payload: SourceDocumentMetadataUpdate,
    db: AsyncSession = Depends(get_db),
) -> SourceDocument:
    document = await db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    await db.commit()
    await db.refresh(document)
    return document


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    document = await db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    storage = get_storage()
    if document.local_path:
        storage.delete(document.local_path)
    await db.delete(document)
    await db.commit()


@router.post("/documents/{document_id}/reprocess", response_model=JobRead, status_code=202)
async def reprocess_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Job:
    document = await db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.local_path:
        raise HTTPException(status_code=400, detail="Document has no stored file to reprocess")

    storage = get_storage()
    content = storage.read_bytes(document.local_path)
    holding_path = storage.save_bytes("uploads", content, suffix="-reprocess")

    job = Job(
        job_type="document_ingestion",
        project_id=document.project_id,
        status=JobStatus.QUEUED,
        current_stage="queued",
    )
    db.add(job)

    # Remove chunks and the old document row; reprocessing re-creates both from
    # the same bytes so citations/ids stay internally consistent rather than
    # silently duplicating alongside a stale document.
    await db.delete(document)
    await db.commit()
    await db.refresh(job)

    await enqueue_job(
        db,
        job,
        process_upload_task,
        str(job.id),
        str(document.project_id) if document.project_id else "",
        document.original_filename or "upload",
        holding_path,
        document.collection_type.value,
        document.confidentiality_level.value,
        document.title,
        document.issuer,
        document.jurisdiction,
    )

    return job
