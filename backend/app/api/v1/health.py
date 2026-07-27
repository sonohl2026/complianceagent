import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a health probe
        db_ok = False
        # Server-side only (Render's Logs tab), never in the response body --
        # this is a public, unauthenticated endpoint, and the exception can
        # include connection/host details.
        logger.error("Health check DB probe failed: %s: %s", type(exc).__name__, exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
    }
