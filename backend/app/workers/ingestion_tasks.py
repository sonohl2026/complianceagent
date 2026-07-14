import asyncio
import uuid
from datetime import datetime, timezone

from app.database import create_worker_engine_and_sessionmaker
from app.models.enums import AuthorityLevel, CollectionType, ConfidentialityLevel, JobStatus, ParseStatus
from app.models.job import Job
from app.services.embeddings.indexing import embed_document
from app.services.parsing.ingestion import ingest_upload
from app.services.storage.file_storage import get_storage
from app.workers.celery_app import celery_app


@celery_app.task(name="ingestion.process_upload")
def process_upload_task(
    job_id: str,
    project_id: str,
    filename: str,
    holding_path: str,
    collection_type: str,
    confidentiality_level: str,
    title: str | None = None,
    issuer: str | None = None,
    jurisdiction: str | None = None,
    authority_level: str | None = None,
    source_type: str | None = None,
    url: str | None = None,
) -> None:
    asyncio.run(
        _process_upload(
            job_id,
            project_id,
            filename,
            holding_path,
            collection_type,
            confidentiality_level,
            title,
            issuer,
            jurisdiction,
            authority_level,
            source_type,
            url,
        )
    )


async def _process_upload(
    job_id: str,
    project_id: str,
    filename: str,
    holding_path: str,
    collection_type: str,
    confidentiality_level: str,
    title: str | None,
    issuer: str | None,
    jurisdiction: str | None,
    authority_level: str | None = None,
    source_type: str | None = None,
    url: str | None = None,
) -> None:
    storage = get_storage()
    engine, SessionLocal = create_worker_engine_and_sessionmaker()
    try:
        async with SessionLocal() as db:
            job = await db.get(Job, uuid.UUID(job_id))
            if job is None:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.current_stage = "parsing"
            await db.commit()

            try:
                content = storage.read_bytes(holding_path)
            except FileNotFoundError:
                job.status = JobStatus.FAILED
                job.error_summary = "Uploaded file was not found in temporary holding storage"
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            try:
                result = await ingest_upload(
                    db,
                    filename=filename,
                    content=content,
                    project_id=uuid.UUID(project_id) if project_id else None,
                    collection_type=CollectionType(collection_type),
                    confidentiality_level=ConfidentialityLevel(confidentiality_level),
                    title=title,
                    issuer=issuer,
                    jurisdiction=jurisdiction,
                    authority_level=AuthorityLevel(authority_level) if authority_level else None,
                    source_type=source_type,
                    url=url,
                )
                job.related_id = result.document.id
                job.logs = [
                    *job.logs,
                    {"stage": "chunking", "message": f"Created {result.chunk_count} chunks"},
                ]
                job.progress_percent = 60

                if result.document.parse_status == ParseStatus.COMPLETE and result.chunk_count:
                    job.current_stage = "embedding"
                    job.progress_percent = 70
                    await db.commit()
                    embedded_count = await embed_document(db, result.document)
                    job.logs = [
                        *job.logs,
                        {"stage": "embedding", "message": f"Embedded {embedded_count} chunks"},
                    ]

                job.status = JobStatus.COMPLETE
                job.progress_percent = 100
                job.current_stage = "complete"
            except Exception as exc:  # noqa: BLE001 - surface any parser/storage/embedding failure to the Job record
                job.status = JobStatus.FAILED
                job.error_summary = str(exc)
            finally:
                storage.delete(holding_path)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        await engine.dispose()
