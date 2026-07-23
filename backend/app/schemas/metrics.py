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
    # Reflects CURRENT Settings config, not the sampled historical runs --
    # see app/services/quick_scan/model_tier.py. False means Stage 1 and
    # Stage 3 are (or were, at query time) silently sharing one model.
    tier_split_active: bool
