import pytest

from app.services.quick_scan.metrics import RunSample, aggregate, percentile


def test_percentile_empty_is_none():
    assert percentile([], 50) is None


def test_percentile_nearest_rank():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 50) == 30.0
    assert percentile(values, 95) == 50.0
    assert percentile(values, 0) == 10.0


def test_aggregate_empty_returns_none_not_zero():
    result = aggregate([])
    assert result["sample_size"] == 0
    assert result["wall_clock_p50_seconds"] is None
    assert result["cost_p50_usd"] is None
    assert result["not_scored_rate"] is None
    assert result["repair_fire_rate"] is None
    assert result["repair_rejected_count"] == 0


def test_aggregate_wall_clock_and_cost():
    samples = [
        RunSample(wall_clock_seconds=10.0, cost_usd=0.05, not_scored=False, token_usage={}),
        RunSample(wall_clock_seconds=20.0, cost_usd=0.10, not_scored=True, token_usage={}),
        RunSample(wall_clock_seconds=30.0, cost_usd=0.15, not_scored=False, token_usage={}),
    ]
    result = aggregate(samples)
    assert result["sample_size"] == 3
    assert result["wall_clock_p50_seconds"] == 20.0
    assert result["cost_p50_usd"] == 0.10
    assert result["cost_mean_usd"] == pytest.approx(0.10)
    assert result["not_scored_rate"] == 1 / 3


def test_aggregate_ignores_missing_wall_clock_and_cost():
    samples = [
        RunSample(wall_clock_seconds=None, cost_usd=None, not_scored=False, token_usage={}),
        RunSample(wall_clock_seconds=10.0, cost_usd=0.05, not_scored=False, token_usage={}),
    ]
    result = aggregate(samples)
    assert result["wall_clock_p50_seconds"] == 10.0
    assert result["cost_p50_usd"] == 0.05


def test_aggregate_sums_stage_token_totals():
    samples = [
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage1_extraction": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
        ),
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage1_extraction": {"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60}},
        ),
    ]
    result = aggregate(samples)
    assert result["stage_token_totals"]["stage1_extraction"] == {
        "prompt_tokens": 150, "completion_tokens": 30, "total_tokens": 180,
        "cached_tokens": 0, "cache_write_tokens": 0,
    }


def test_aggregate_sums_cached_tokens_and_tolerates_missing_ones(): # spec §7: cached-vs-uncached tracking
    samples = [
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage3_synthesis": {
                "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                "cached_tokens": 80, "cache_write_tokens": 0,
            }},
        ),
        RunSample(
            # No prompt-caching details on this response at all (not every
            # call gets a cache hit/write) -- must not crash the running sum.
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage3_synthesis": {
                "prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60,
                "cached_tokens": None, "cache_write_tokens": None,
            }},
        ),
    ]
    result = aggregate(samples)
    assert result["stage_token_totals"]["stage3_synthesis"]["cached_tokens"] == 80
    assert result["stage_token_totals"]["stage3_synthesis"]["cache_write_tokens"] == 0


def test_aggregate_repair_fire_rate_and_rejected_count():  # spec §7's "going forward" monitored metrics
    samples = [
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage3_synthesis": {"repair_fired": True, "repair_rejected": True}},
        ),
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage3_synthesis": {"repair_fired": True, "repair_rejected": False}},
        ),
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage3_synthesis": {"repair_fired": False, "repair_rejected": False}},
        ),
        RunSample(
            # Older records with no repair fields at all must not crash --
            # counted as no-repair, not skipped.
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={"stage3_synthesis": {"prompt_tokens": 10}},
        ),
    ]
    result = aggregate(samples)
    assert result["repair_fire_rate"] == 2 / 4
    assert result["repair_rejected_count"] == 1


def test_aggregate_repair_fired_on_any_stage_counts_the_run():
    samples = [
        RunSample(
            wall_clock_seconds=1.0, cost_usd=0.01, not_scored=False,
            token_usage={
                "stage1_extraction": {"repair_fired": False},
                "stage3_synthesis": {"repair_fired": True},
            },
        ),
    ]
    result = aggregate(samples)
    assert result["repair_fire_rate"] == 1.0
