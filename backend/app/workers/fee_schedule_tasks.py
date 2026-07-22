import asyncio

import httpx

from app.services.fee_schedule import refresh
from app.workers.celery_app import celery_app


@celery_app.task(name="fee_schedule.refresh_pfs")
def refresh_pfs_task() -> None:
    asyncio.run(_refresh_pfs())


async def _refresh_pfs() -> None:
    async with httpx.AsyncClient() as client:
        await refresh.refresh_pfs(client)
