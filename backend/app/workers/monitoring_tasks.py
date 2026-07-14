import asyncio

from app.database import create_worker_engine_and_sessionmaker
from app.services.monitoring.scheduling import dispatch_due_schedules
from app.workers.celery_app import celery_app


@celery_app.task(name="monitoring.dispatch_due_recrawls")
def dispatch_due_recrawls_task() -> None:
    asyncio.run(_dispatch_due_recrawls())


async def _dispatch_due_recrawls() -> None:
    engine, SessionLocal = create_worker_engine_and_sessionmaker()
    try:
        async with SessionLocal() as db:
            await dispatch_due_schedules(db)
    finally:
        await engine.dispose()
