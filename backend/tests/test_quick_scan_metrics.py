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
    assert result["cost_mean_usd"] == 0.10
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
    }
