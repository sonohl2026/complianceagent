"""OpenRouter implementation of LLMProvider (build spec §9).

Design points from the spec, implemented here:
- exact model slug required (no "latest" alias defaulting);
- structured JSON output via response_format json_schema, strict mode;
- one automatic repair retry on schema validation failure, then a terminal
  LLMValidationError (never silently accept malformed output);
- exponential backoff, retrying only on transient failures (rate limit,
  timeout, connection, 5xx) -- never retrying a 4xx client error;
- records requested model, actual returned model id, token usage, latency;
- never logs the API key.
"""

import asyncio
import json
import logging
import time

import jsonschema
import openai

from app.config import get_settings
from app.services.llm.base import LLMProviderError, LLMResult, LLMValidationError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.5


class OpenRouterProvider:
    def __init__(self, api_key: str | None = None, prompt_caching: bool = True):
        settings = get_settings()
        self._settings = settings
        self._api_key = api_key or settings.openrouter_api_key
        # Was previously a fully inert runtime setting (openrouter_prompt_
        # caching existed in Settings, defaulted True, was never read by this
        # class at all) -- confirmed via 9 real Stage-3 calls all reporting
        # cached_tokens=0/cache_write_tokens=0 despite the same large,
        # byte-identical system prompt on every call. Root cause: Anthropic's
        # API (which this flows through unmodified) requires an explicit
        # cache_control breakpoint on the content block to opt in -- content
        # being merely identical across calls does not trigger caching on
        # its own. See _build_system_message below for the actual fix.
        self._prompt_caching = prompt_caching
        if not self._api_key:
            raise LLMProviderError("No OpenRouter API key configured. Set it in Settings first.")

        self._client = openai.AsyncOpenAI(
            api_key=self._api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": settings.openrouter_http_referer,
                "X-Title": settings.openrouter_app_title,
            },
            # No timeout here previously -- the SDK's own default is 600s,
            # a production hang risk (a single stuck request could block a
            # worker for 10 minutes before the existing retry logic even
            # gets a chance to run). 60s is generous above every real
            # latency observed for any single call in this app (typically
            # well under 60s even for full quick_scan Stage 3 synthesis).
            timeout=60.0,
        )

    async def structured_completion(
        self,
        *,
        system_prompt: str,
        messages: list[dict],
        schema: dict,
        schema_name: str,
        model: str,
        temperature: float = 0,
        max_tokens: int = 8000,
        metadata: dict | None = None,
    ) -> LLMResult:
        if not model:
            raise LLMProviderError(
                "No model slug configured. Set an exact OpenRouter model slug in Settings "
                "before running an analysis (e.g. 'anthropic/claude-sonnet-4.5', not a 'latest' alias)."
            )

        full_messages = [self._build_system_message(system_prompt), *messages]
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        }
        extra_body = {}
        if self._settings.openrouter_zdr:
            # Best-effort: ask OpenRouter to route only to zero-data-retention
            # providers. Verify this exact field name against OpenRouter's
            # current API docs periodically -- provider-side API surfaces
            # like this are exactly the kind of "time-sensitive external
            # rule" this whole application is built to never take on faith.
            extra_body["provider"] = {"data_collection": "deny"}

        result = await self._call_with_retry(
            model=model,
            messages=full_messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )

        try:
            parsed = self._parse_and_validate(result, schema)
            return self._to_llm_result(result, parsed, model, schema_repair_attempted=False)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            logger.info("Structured output failed validation for %s, attempting one repair retry: %s", schema_name, exc)
            repair_messages = [
                *full_messages,
                {"role": "assistant", "content": result.choices[0].message.content or ""},
                {
                    "role": "user",
                    "content": (
                        "Your previous response did not validate against the required JSON schema. "
                        f"Validation error: {exc}. Return ONLY corrected JSON matching the schema, "
                        "with no additional commentary."
                    ),
                },
            ]
            repaired = await self._call_with_retry(
                model=model,
                messages=repair_messages,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                extra_body=extra_body,
            )
            try:
                parsed = self._parse_and_validate(repaired, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as second_exc:
                raise LLMValidationError(
                    f"Structured output for {schema_name!r} failed schema validation twice: {second_exc}"
                ) from second_exc
            return self._to_llm_result(repaired, parsed, model, schema_repair_attempted=True)

    def _build_system_message(self, system_prompt: str) -> dict:
        if not self._prompt_caching:
            return {"role": "system", "content": system_prompt}
        # Anthropic (and OpenRouter's pass-through of it) requires an
        # explicit cache_control breakpoint on a content block -- a plain
        # string body, even if byte-identical across every call, is never
        # cached on its own. This marks the whole system prompt (the static,
        # reused-every-call part) as a cache breakpoint.
        return {
            "role": "system",
            "content": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        }

    async def _call_with_retry(self, **kwargs):
        last_exc: Exception | None = None
        temperature_retry_used = False
        for attempt in range(MAX_RETRIES):
            try:
                start = time.monotonic()
                response = await self._client.chat.completions.create(**kwargs)
                response._latency_ms = int((time.monotonic() - start) * 1000)  # noqa: SLF001
                return response
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as exc:
                last_exc = exc
                await asyncio.sleep(BASE_BACKOFF_SECONDS * (2**attempt))
            except openai.InternalServerError as exc:
                last_exc = exc
                await asyncio.sleep(BASE_BACKOFF_SECONDS * (2**attempt))
            except openai.APIStatusError as exc:
                # Some models behind OpenRouter (observed: certain reasoning-style
                # Anthropic models) reject the `temperature` parameter outright
                # rather than just ignoring it. Detected in production against a
                # real OpenRouter response: "`temperature` is deprecated for this
                # model." Strip it and retry once, immediately (not a transient
                # failure, so no backoff), rather than failing the whole analysis.
                if (
                    not temperature_retry_used
                    and "temperature" in kwargs
                    and "temperature" in str(exc).lower()
                ):
                    logger.info(
                        "Model %s rejected the `temperature` parameter; retrying once without it.",
                        kwargs.get("model"),
                    )
                    kwargs = {k: v for k, v in kwargs.items() if k != "temperature"}
                    temperature_retry_used = True
                    continue
                if exc.status_code == 402:
                    # OpenRouter's insufficient-balance response: a real, common
                    # failure mode (observed in production), and the raw error
                    # body is a hard-to-read JSON dump -- surface a clean,
                    # actionable message instead of that dump.
                    raise LLMProviderError(
                        "Your OpenRouter account is out of credits, or doesn't have enough balance "
                        "to cover this request. Add credits at https://openrouter.ai/settings/credits, "
                        "then retry this analysis."
                    ) from exc
                if exc.status_code == 401:
                    raise LLMProviderError(
                        "Your OpenRouter API key was rejected as invalid or expired. Check the key in "
                        "Settings, then retry this analysis."
                    ) from exc
                # Other 4xx client errors (bad request, model not found) are not retryable.
                raise LLMProviderError(f"OpenRouter request failed ({exc.status_code}): {exc.message}") from exc
        raise LLMProviderError(f"OpenRouter request failed after {MAX_RETRIES} attempts: {last_exc}")

    @staticmethod
    def _parse_and_validate(response, schema: dict) -> dict:
        raw_content = response.choices[0].message.content or ""
        parsed = json.loads(raw_content)
        jsonschema.validate(instance=parsed, schema=schema)
        return parsed

    @staticmethod
    def _to_llm_result(response, parsed: dict, requested_model: str, *, schema_repair_attempted: bool) -> LLMResult:
        usage = response.usage
        cost_usd = None
        metadata = {}
        if hasattr(response, "usage") and usage is not None:
            cost_usd = getattr(usage, "cost", None)
            # OpenRouter/OpenAI-SDK extension field, not on every provider's
            # response -- confirmed present (verified against a real call)
            # but only non-zero when prompt caching actually took effect.
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            if prompt_details is not None:
                metadata["cached_tokens"] = getattr(prompt_details, "cached_tokens", None)
                metadata["cache_write_tokens"] = getattr(prompt_details, "cache_write_tokens", None)
        return LLMResult(
            content=parsed,
            raw_content=response.choices[0].message.content or "",
            requested_model=requested_model,
            model_response_identifier=getattr(response, "model", None),
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            cost_usd=cost_usd,
            latency_ms=getattr(response, "_latency_ms", 0),
            finish_reason=response.choices[0].finish_reason if response.choices else None,
            schema_repair_attempted=schema_repair_attempted,
            metadata=metadata,
        )
