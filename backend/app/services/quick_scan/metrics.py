"""Pure aggregation math for GET /metrics (v2 spec §7) -- kept separate from
the FastAPI route so the percentile logic has a cheap, no-DB/HTTP unit test
(app/api/v1/metrics.py owns fetching the rows and shaping the response)."""

from __future__ import annotations

import math
from dataclasses import dataclass


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile (pct in [0, 100]). None on an empty input --
    callers decide how to render "no data" rather than this silently
    returning 0, which would be indistinguishable from a genuine 0-second/
    $0 run."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil((pct / 100) * len(ordered)))
    return ordered[rank - 1]


@dataclass
class RunSample:
    wall_clock_seconds: float | None
    cost_usd: float | None
    not_scored: bool
    token_usage: dict[str, dict[str, int]]


def _any_stage_flag(token_usage: dict[str, dict], flag: str) -> bool:
    return any(usage.get(flag) for usage in token_usage.values())


def aggregate(samples: list[RunSample]) -> dict:
    wall_clock = [s.wall_clock_seconds for s in samples if s.wall_clock_seconds is not None]
    costs = [s.cost_usd for s in samples if s.cost_usd is not None]

    # First-class per Step 4d of the close-out: a repair pass firing was
    # previously invisible in every persisted record (see the blast-radius
    # audit in the close-out report) -- these are the "going forward"
    # monitored metrics so a regression here is visible in /metrics instead
    # of resurfacing as a mystery p95 breach.
    repair_fired_count = sum(1 for s in samples if _any_stage_flag(s.token_usage, "repair_fired"))
    repair_rejected_count = sum(1 for s in samples if _any_stage_flag(s.token_usage, "repair_rejected"))

    # cached_tokens/cache_write_tokens are None whenever a stage's response
    # didn't report prompt-caching details at all (not every call gets a
    # cache hit/write, and not every provider surfaces the field) -- summed
    # as 0 in that case rather than breaking the running total, but see
    # note below: a stage where EVERY sample was None gets 0, not None,
    # since these are running sums, not an aggregate.
    _STAGE_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "cache_write_tokens")
    stage_totals: dict[str, dict[str, int]] = {}
    for s in samples:
        for stage, usage in s.token_usage.items():
            bucket = stage_totals.setdefault(stage, {key: 0 for key in _STAGE_KEYS})
            for key in bucket:
                bucket[key] += usage.get(key, 0) or 0

    return {
        "sample_size": len(samples),
        "wall_clock_p50_seconds": percentile(wall_clock, 50),
        "wall_clock_p95_seconds": percentile(wall_clock, 95),
        "cost_p50_usd": percentile(costs, 50),
        "cost_p95_usd": percentile(costs, 95),
        "cost_mean_usd": (sum(costs) / len(costs)) if costs else None,
        "not_scored_rate": (sum(1 for s in samples if s.not_scored) / len(samples)) if samples else None,
        "repair_fire_rate": (repair_fired_count / len(samples)) if samples else None,
        "repair_rejected_count": repair_rejected_count,
        "stage_token_totals": stage_totals,
    }
