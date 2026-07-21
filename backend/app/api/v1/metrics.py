"""GET /metrics (v2 spec §7): aggregates the last N completed quick_scan runs
so Task 4/6's own real-run AC (<=$0.10 and <30s p50) can be checked from the
running app itself, not just from a one-off `make bench` printout."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.analysis import AnalysisRun
from app.models.enums import JobStatus
from app.schemas.metrics import QuickScanMetrics
from app.services.quick_scan.metrics import RunSample, aggregate

router = APIRouter()

_SAMPLE_SIZE = 50


@router.get("/metrics/quick-scan", response_model=QuickScanMetrics)
async def get_quick_scan_metrics(db: AsyncSession = Depends(get_db)) -> QuickScanMetrics:
    rows = (
        (
            await db.execute(
                select(AnalysisRun)
                .where(AnalysisRun.analysis_type == "quick_scan", AnalysisRun.status == JobStatus.COMPLETE)
                .order_by(AnalysisRun.created_at.desc())
                .limit(_SAMPLE_SIZE)
            )
        )
        .scalars()
        .all()
    )

    samples = [
        RunSample(
            wall_clock_seconds=(
                (run.completed_at - run.started_at).total_seconds()
                if run.completed_at and run.started_at
                else None
            ),
            cost_usd=sum(run.cost_json.values()) if run.cost_json else None,
            not_scored=run.quick_scan_result_json.get("scores", {}).get("maturity_state") == "NOT_SCORED",
            token_usage=run.token_usage_json,
        )
        for run in rows
    ]

    return QuickScanMetrics(**aggregate(samples))
