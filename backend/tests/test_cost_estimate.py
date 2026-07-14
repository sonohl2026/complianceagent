import httpx
import pytest
import respx

from app.services.llm.cost_estimate import STAGE_MAX_TOKENS, preflight_credit_check

CREDITS_URL = "https://openrouter.ai/api/v1/credits"
MODELS_URL = "https://openrouter.ai/api/v1/models"


def _models_response(model_id: str, completion_price: str) -> dict:
    return {"data": [{"id": model_id, "pricing": {"prompt": "0.000003", "completion": completion_price}}]}


@pytest.mark.asyncio
@respx.mock
async def test_sufficient_balance_returns_no_error():
    respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(200, json={"data": {"total_credits": 100.0, "total_usage": 1.0}})
    )
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json=_models_response("anthropic/claude-opus-4.8", "0.0001"))
    )
    result = await preflight_credit_check("sk-test", "anthropic/claude-opus-4.8")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_insufficient_balance_returns_clear_actionable_message():
    # Real scenario this fixes: account nearly empty, would fail partway
    # through a multi-stage run -- catch it before any stage starts.
    respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(200, json={"data": {"total_credits": 5.0, "total_usage": 4.99}})
    )
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json=_models_response("anthropic/claude-opus-4.8", "0.0001"))
    )
    result = await preflight_credit_check("sk-test", "anthropic/claude-opus-4.8")
    assert result is not None
    assert "$0.01" in result
    assert "openrouter.ai/settings/credits" in result
    expected_floor = sum(STAGE_MAX_TOKENS.values()) * 0.0001
    assert f"${expected_floor:.2f}" in result


@pytest.mark.asyncio
@respx.mock
async def test_zero_balance_returns_error():
    respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(200, json={"data": {"total_credits": 10.0, "total_usage": 10.0}})
    )
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json=_models_response("anthropic/claude-opus-4.8", "0.0001"))
    )
    result = await preflight_credit_check("sk-test", "anthropic/claude-opus-4.8")
    assert result is not None
    assert "$0.00" in result


@pytest.mark.asyncio
@respx.mock
async def test_openrouter_error_fails_open_not_raises():
    respx.get(CREDITS_URL).mock(return_value=httpx.Response(500))
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json=_models_response("anthropic/claude-opus-4.8", "0.0001"))
    )
    result = await preflight_credit_check("sk-test", "anthropic/claude-opus-4.8")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_unknown_model_fails_open_not_raises():
    respx.get(CREDITS_URL).mock(
        return_value=httpx.Response(200, json={"data": {"total_credits": 0.0, "total_usage": 0.0}})
    )
    respx.get(MODELS_URL).mock(return_value=httpx.Response(200, json={"data": []}))
    result = await preflight_credit_check("sk-test", "some/unlisted-model")
    assert result is None


@pytest.mark.asyncio
@respx.mock
async def test_unexpected_response_shape_fails_open_not_raises():
    respx.get(CREDITS_URL).mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))
    respx.get(MODELS_URL).mock(
        return_value=httpx.Response(200, json=_models_response("anthropic/claude-opus-4.8", "0.0001"))
    )
    result = await preflight_credit_check("sk-test", "anthropic/claude-opus-4.8")
    assert result is None
