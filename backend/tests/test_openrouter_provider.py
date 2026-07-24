import json

import httpx
import pytest
import respx

from app.services.llm.base import LLMProviderError, LLMValidationError
from app.services.llm.openrouter_provider import OpenRouterProvider

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string"}, "risk": {"type": "string"}},
    "required": ["verdict", "risk"],
    "additionalProperties": False,
}


def _chat_response(content: dict, *, model="anthropic/claude-sonnet-4.5", finish_reason="stop") -> dict:
    return {
        "id": "gen-123",
        "model": model,
        "choices": [
            {
                "message": {"role": "assistant", "content": json.dumps(content)},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


def _provider(prompt_caching: bool = True) -> OpenRouterProvider:
    return OpenRouterProvider(api_key="sk-or-test-key", prompt_caching=prompt_caching)


# --- prompt caching (previously a fully inert setting -- see
# openrouter_provider.py's constructor comment; confirmed via 9 real Stage-3
# calls all reporting cached_tokens=0 despite an identical, large system
# prompt on every call) ---

@respx.mock
async def test_prompt_caching_on_sends_cache_control_breakpoint():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({"verdict": "GO", "risk": "LOW"}))
    )
    provider = _provider(prompt_caching=True)
    await provider.structured_completion(
        system_prompt="a long, reused system prompt",
        messages=[{"role": "user", "content": "hi"}],
        schema=SCHEMA, schema_name="test_schema", model="anthropic/claude-sonnet-4.5",
    )
    sent_body = json.loads(route.calls.last.request.content)
    system_message = sent_body["messages"][0]
    assert system_message["role"] == "system"
    assert system_message["content"] == [
        {"type": "text", "text": "a long, reused system prompt", "cache_control": {"type": "ephemeral"}}
    ]


@respx.mock
async def test_prompt_caching_off_sends_plain_string():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({"verdict": "GO", "risk": "LOW"}))
    )
    provider = _provider(prompt_caching=False)
    await provider.structured_completion(
        system_prompt="a long, reused system prompt",
        messages=[{"role": "user", "content": "hi"}],
        schema=SCHEMA, schema_name="test_schema", model="anthropic/claude-sonnet-4.5",
    )
    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["messages"][0] == {"role": "system", "content": "a long, reused system prompt"}


# --- truncate-not-retry + repair-path integrity guard (added after a real
# incident: repair passes were silently rewriting whole pillars' findings,
# not just the field that actually violated the schema -- see conversation
# record. Root cause: the deployed repair prompt had silently dropped spec
# §2's own "change no values" clause. Fixed two ways: (1) a maxLength
# violation -- confirmed the dominant real-world case -- never needs an LLM
# round-trip at all now; (2) any repair that IS attempted is diffed against
# the first-pass content and rejected if it touches anything the validation
# error didn't name. ---

_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "detail": {"type": "string", "maxLength": 20},
                    "status": {"enum": ["OK", "BAD"]},
                },
                "required": ["name", "detail", "status"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}


@respx.mock
async def test_maxlength_violation_fixed_by_truncation_no_llm_repair_call():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({
            "items": [{"name": "a", "detail": "this description is way too long for the cap", "status": "OK"}],
        }))
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys", messages=[{"role": "user", "content": "go"}],
        schema=_ITEMS_SCHEMA, schema_name="items_schema", model="anthropic/claude-sonnet-4.5",
    )
    assert route.call_count == 1  # no LLM repair round-trip at all
    assert result.schema_repair_attempted is False
    assert len(result.content["items"][0]["detail"]) <= 20
    assert result.content["items"][0]["detail"].endswith("…")
    assert result.content["items"][0]["name"] == "a"  # untouched field survives


@respx.mock
async def test_multiple_maxlength_violations_all_fixed_by_truncation():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({
            "items": [
                {"name": "a", "detail": "this first description is way too long for the cap", "status": "OK"},
                {"name": "b", "detail": "this second description is also way too long for the cap", "status": "BAD"},
            ],
        }))
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys", messages=[{"role": "user", "content": "go"}],
        schema=_ITEMS_SCHEMA, schema_name="items_schema", model="anthropic/claude-sonnet-4.5",
    )
    assert route.call_count == 1
    assert result.schema_repair_attempted is False
    assert all(len(item["detail"]) <= 20 for item in result.content["items"])


@respx.mock
async def test_enum_violation_not_truncation_fixable_falls_through_to_repair():
    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "short", "status": "MAYBE"}]})),
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "short", "status": "OK"}]})),
        ]
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys", messages=[{"role": "user", "content": "go"}],
        schema=_ITEMS_SCHEMA, schema_name="items_schema", model="anthropic/claude-sonnet-4.5",
    )
    assert result.schema_repair_attempted is True
    assert result.content["items"][0]["status"] == "OK"
    assert result.repair_rejected is False


@respx.mock
async def test_compliant_repair_accepted_when_it_only_touches_the_violating_field():
    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "short", "status": "MAYBE"}]})),
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "short", "status": "OK"}]})),
        ]
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys", messages=[{"role": "user", "content": "go"}],
        schema=_ITEMS_SCHEMA, schema_name="items_schema", model="anthropic/claude-sonnet-4.5",
    )
    assert result.repair_rejected is False
    assert result.content == {"items": [{"name": "a", "detail": "short", "status": "OK"}]}


@respx.mock
async def test_value_altering_repair_rejected_then_succeeds_on_retry():
    # First repair fixes the enum violation but ALSO rewrites "detail"
    # (unauthorized) -- must be rejected and retried; second repair fixes
    # it properly.
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "original text", "status": "MAYBE"}]})),
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "REWRITTEN", "status": "OK"}]})),
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "original text", "status": "OK"}]})),
        ]
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys", messages=[{"role": "user", "content": "go"}],
        schema=_ITEMS_SCHEMA, schema_name="items_schema", model="anthropic/claude-sonnet-4.5",
    )
    assert route.call_count == 3  # first-pass + rejected repair + retry
    assert result.repair_rejected is True
    assert result.content == {"items": [{"name": "a", "detail": "original text", "status": "OK"}]}


@respx.mock
async def test_value_altering_repair_still_wrong_after_retry_raises_hard_error():
    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "original text", "status": "MAYBE"}]})),
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "REWRITTEN ONCE", "status": "OK"}]})),
            httpx.Response(200, json=_chat_response({"items": [{"name": "a", "detail": "REWRITTEN AGAIN", "status": "OK"}]})),
        ]
    )
    provider = _provider()
    with pytest.raises(LLMValidationError, match="refusing to return a silently rewritten assessment"):
        await provider.structured_completion(
            system_prompt="sys", messages=[{"role": "user", "content": "go"}],
            schema=_ITEMS_SCHEMA, schema_name="items_schema", model="anthropic/claude-sonnet-4.5",
        )


@respx.mock
async def test_structured_completion_returns_parsed_content():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({"verdict": "CONDITIONAL_GO", "risk": "HIGH"}))
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="You are a compliance agent.",
        messages=[{"role": "user", "content": "Analyze this."}],
        schema=SCHEMA,
        schema_name="test_schema",
        model="anthropic/claude-sonnet-4.5",
    )
    assert result.content == {"verdict": "CONDITIONAL_GO", "risk": "HIGH"}
    assert result.model_response_identifier == "anthropic/claude-sonnet-4.5"
    assert result.total_tokens == 120
    assert result.schema_repair_attempted is False


@respx.mock
async def test_missing_required_field_triggers_repair_retry_then_succeeds():
    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_response({"verdict": "STOP"})),  # missing "risk" -> invalid
            httpx.Response(200, json=_chat_response({"verdict": "STOP", "risk": "CRITICAL"})),
        ]
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="test_schema",
        model="anthropic/claude-sonnet-4.5",
    )
    assert result.content == {"verdict": "STOP", "risk": "CRITICAL"}
    assert result.schema_repair_attempted is True


@respx.mock
async def test_invalid_output_twice_raises_validation_error():
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({"verdict": "STOP"}))  # always missing "risk"
    )
    provider = _provider()
    with pytest.raises(LLMValidationError):
        await provider.structured_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="test_schema",
            model="anthropic/claude-sonnet-4.5",
        )


@respx.mock
async def test_client_error_is_not_retried():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(401, json={"error": {"message": "Invalid API key"}})
    )
    provider = _provider()
    with pytest.raises(LLMProviderError):
        await provider.structured_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="test_schema",
            model="anthropic/claude-sonnet-4.5",
        )
    assert route.call_count == 1  # no retry on a 4xx


@respx.mock
async def test_rate_limit_is_retried_then_succeeds():
    respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "rate limited"}}),
            httpx.Response(200, json=_chat_response({"verdict": "GO", "risk": "LOW"})),
        ]
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="test_schema",
        model="anthropic/claude-sonnet-4.5",
    )
    assert result.content == {"verdict": "GO", "risk": "LOW"}


async def test_missing_model_raises_without_any_network_call():
    provider = _provider()
    with pytest.raises(LLMProviderError, match="No model slug"):
        await provider.structured_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="test_schema",
            model="",
        )


def test_missing_api_key_raises_at_construction(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(LLMProviderError):
            OpenRouterProvider(api_key="")
    finally:
        get_settings.cache_clear()


@respx.mock
async def test_temperature_rejection_is_retried_without_it():
    # Reproduces a real failure seen against OpenRouter: a reasoning-style
    # model rejects `temperature` outright rather than ignoring it.
    error_body = {
        "error": {
            "message": (
                'Provider returned error {"type":"error","error":{"type":"invalid_request_error",'
                '"message":"`temperature` is deprecated for this model."}}'
            )
        }
    }
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(400, json=error_body),
            httpx.Response(200, json=_chat_response({"verdict": "GO", "risk": "LOW"})),
        ]
    )
    provider = _provider()
    result = await provider.structured_completion(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="test_schema",
        model="anthropic/claude-opus-4.8",
    )
    assert result.content == {"verdict": "GO", "risk": "LOW"}
    assert route.call_count == 2
    second_request_body = json.loads(route.calls[1].request.content)
    assert "temperature" not in second_request_body


@respx.mock
async def test_temperature_rejection_only_retried_once():
    # If the provider keeps rejecting temperature even after it's removed
    # (a different underlying issue), this must not loop forever.
    error_body = {
        "error": {"message": '{"error":{"message":"`temperature` is deprecated for this model."}}'}
    }
    route = respx.post(CHAT_URL).mock(return_value=httpx.Response(400, json=error_body))
    provider = _provider()
    with pytest.raises(LLMProviderError):
        await provider.structured_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="test_schema",
            model="anthropic/claude-opus-4.8",
        )
    assert route.call_count == 2  # one original attempt + one temperature-stripped retry, then give up


@respx.mock
async def test_insufficient_credits_produces_clean_actionable_message():
    # Real incident: OpenRouter's 402 response is a hard-to-read raw JSON
    # dump ("This request requires more credits..."); users should see a
    # clear, actionable message instead.
    error_body = {"error": {"message": "This request requires more credits, or fewer max_tokens."}}
    respx.post(CHAT_URL).mock(return_value=httpx.Response(402, json=error_body))
    provider = _provider()
    with pytest.raises(LLMProviderError) as exc_info:
        await provider.structured_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="test_schema",
            model="anthropic/claude-opus-4.8",
        )
    message = str(exc_info.value)
    assert "out of credits" in message
    assert "openrouter.ai/settings/credits" in message


@respx.mock
async def test_invalid_api_key_produces_clean_actionable_message():
    error_body = {"error": {"message": "No auth credentials found"}}
    respx.post(CHAT_URL).mock(return_value=httpx.Response(401, json=error_body))
    provider = _provider()
    with pytest.raises(LLMProviderError) as exc_info:
        await provider.structured_completion(
            system_prompt="sys",
            messages=[{"role": "user", "content": "go"}],
            schema=SCHEMA,
            schema_name="test_schema",
            model="anthropic/claude-opus-4.8",
        )
    assert "rejected as invalid or expired" in str(exc_info.value)


@respx.mock
async def test_default_max_tokens_is_bounded_not_left_to_model_default():
    # Real incident: leaving max_tokens unset let it default to a model's
    # absolute max (65536), which made OpenRouter pre-authorize credits for
    # that worst case and reject the request as unaffordable even though
    # actual usage would be far smaller. Every request must send an explicit,
    # bounded max_tokens.
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({"verdict": "GO", "risk": "LOW"}))
    )
    provider = _provider()
    await provider.structured_completion(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="test_schema",
        model="anthropic/claude-opus-4.8",
    )
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body.get("max_tokens") == 8000


@respx.mock
async def test_max_tokens_override_is_respected():
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_chat_response({"verdict": "GO", "risk": "LOW"}))
    )
    provider = _provider()
    await provider.structured_completion(
        system_prompt="sys",
        messages=[{"role": "user", "content": "go"}],
        schema=SCHEMA,
        schema_name="test_schema",
        model="anthropic/claude-opus-4.8",
        max_tokens=12000,
    )
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body.get("max_tokens") == 12000
