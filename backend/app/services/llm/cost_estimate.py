"""Pre-flight OpenRouter balance check (user-requested: catch a doomed
analysis in under a second, not after 3-4 of 11 stages have already run).

Predicting the *exact* cost of a full analysis ahead of time isn't possible
-- actual prompt-token usage depends on how much evidence gets retrieved for
each stage, and can grow further if a stage needs its one schema-repair
retry. What IS knowable ahead of time, with two cheap HTTP calls to
OpenRouter (account balance + published per-token pricing), is a worst-case
*completion*-token cost floor: every stage sends an explicit max_tokens cap
(see app/services/analysis/pipeline.py), so summing
(max_tokens * completion_price) across all 11 stages is a hard lower bound
on what the full pipeline could cost -- prompt tokens are always additional
on top of that floor, never counted against it.

If the account's remaining balance can't even cover that floor, the full
analysis is *certain* to fail partway through on a 402. This module exists
to catch exactly that, before any stage runs.

Deliberately fails open: OpenRouter's balance/pricing response shapes are
exactly the kind of "time-sensitive external API surface" that can drift
(verify periodically against https://openrouter.ai/docs) -- any error here
is swallowed and the analysis is allowed to proceed as it would without this
check, rather than blocking a legitimate run over a wrong assumption about a
response shape.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

# Mirrors the max_tokens actually sent for each stage in
# app/services/analysis/pipeline.py -- kept here rather than imported to
# avoid a circular import, and because this only needs to be a worst-case
# floor, not byte-for-byte in sync with the pipeline.
STAGE_MAX_TOKENS = {
    "input_audit": 8000,
    "product_fact_extraction": 8000,
    "claim_extraction": 12000,
    "coding_analysis": 12000,
    # regulatory/coverage/payment/billing/marketing analysis were 5 separate
    # 12000-token stages; now one combined call (see
    # app.services.analysis.pipeline.COMBINED_DOMAIN_MAX_TOKENS).
    "domain_analysis": 28000,
    "synthesis": 8000,
    "citation_audit": 8000,
}

# quick_scan (app/services/quick_scan/{stage1_extraction,stage3_synthesis}.py)
# is a completely different, much smaller pipeline -- 2 LLM stages, not 7 --
# so it needs its own floor. Reusing STAGE_MAX_TOKENS here would overestimate
# quick_scan's minimum cost by ~30x and wrongly block runs on a perfectly
# adequate balance.
QUICK_SCAN_STAGE_MAX_TOKENS = {
    "stage1_extraction": 500,
    "stage3_synthesis": 2000,
}


async def _get_remaining_balance_usd(client: httpx.AsyncClient, api_key: str) -> float | None:
    response = await client.get(
        "https://openrouter.ai/api/v1/credits", headers={"Authorization": f"Bearer {api_key}"}
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    total_credits = data.get("total_credits")
    total_usage = data.get("total_usage")
    if total_credits is None or total_usage is None:
        return None
    return float(total_credits) - float(total_usage)


async def _get_completion_price_per_token(client: httpx.AsyncClient, api_key: str, model: str) -> float | None:
    response = await client.get(
        "https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {api_key}"}
    )
    response.raise_for_status()
    for entry in response.json().get("data", []):
        if entry.get("id") == model:
            price = (entry.get("pricing") or {}).get("completion")
            return float(price) if price is not None else None
    return None


async def preflight_credit_check(
    api_key: str, model: str, stage_max_tokens: dict[str, int] | None = None
) -> str | None:
    """Returns a user-facing error message if the account's balance is
    clearly insufficient to complete a full analysis, else None. Never
    raises -- any failure to determine balance/pricing just skips the
    check (fail open).

    stage_max_tokens defaults to the old document-driven pipeline's
    STAGE_MAX_TOKENS; pass QUICK_SCAN_STAGE_MAX_TOKENS for quick_scan runs,
    whose much smaller 2-stage budget would otherwise be checked against a
    ~30x-too-large floor."""
    if stage_max_tokens is None:
        stage_max_tokens = STAGE_MAX_TOKENS
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            remaining = await _get_remaining_balance_usd(client, api_key)
            price_per_token = await _get_completion_price_per_token(client, api_key, model)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.info("Pre-flight OpenRouter balance check skipped (could not determine balance/pricing): %s", exc)
        return None

    if remaining is None or price_per_token is None:
        return None

    minimum_cost = sum(stage_max_tokens.values()) * price_per_token
    if remaining < minimum_cost:
        return (
            f"Your OpenRouter balance (${remaining:.2f}) is below the estimated minimum cost of a full "
            f"analysis with this model (at least ${minimum_cost:.2f} in completion tokens alone, before "
            "any input/prompt tokens are even counted). This analysis would very likely fail partway "
            "through. Add credits at https://openrouter.ai/settings/credits before running it."
        )
    return None
