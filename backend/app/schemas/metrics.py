from pydantic import BaseModel


class QuickScanMetrics(BaseModel):
    sample_size: int
    wall_clock_p50_seconds: float | None
    wall_clock_p95_seconds: float | None
    cost_p50_usd: float | None
    cost_p95_usd: float | None
    cost_mean_usd: float | None
    not_scored_rate: float | None
    stage_token_totals: dict[str, dict[str, int]]
