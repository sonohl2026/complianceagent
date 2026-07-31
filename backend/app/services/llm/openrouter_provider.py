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
_MAX_TRUNCATION_ITERATIONS = 10  # generous headroom above the ~6 length-capped
# string fields a real quick_scan response can have; just a loop-safety cap.
_TRUNCATION_RETRY_MULTIPLIER = 1.5  # how much more budget to give a response
# that got cut off mid-generation (finish_reason == "length") before falling
# back to the same-budget repair path, which would otherwise fail the same way.


def _truncate_to_word_boundary(text: str, max_length: int) -> str:
    """Deterministic fix for a maxLength violation -- no LLM round-trip.
    Cuts at the last word boundary within budget and appends an ellipsis, so
    the result never exceeds max_length and never ends mid-word."""
    if len(text) <= max_length:
        return text
    ellipsis = "…"
    budget = max_length - len(ellipsis)
    if budget <= 0:
        return ellipsis[:max_length]
    truncated = text[:budget]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + ellipsis


def _apply_truncation_fix(parsed: dict, error: "jsonschema.ValidationError") -> bool:
    """Mutates parsed in place to fix ONE maxLength violation. Returns False
    (no mutation) for any other violation type -- structural/missing-field/
    enum violations aren't truncation-fixable and must fall through to the
    LLM repair pass."""
    if error.validator != "maxLength":
        return False
    path = list(error.absolute_path)
    if not path:
        return False
    target = parsed
    for key in path[:-1]:
        target = target[key]
    last_key = path[-1]
    current_value = target[last_key]
    if not isinstance(current_value, str):
        return False
    target[last_key] = _truncate_to_word_boundary(current_value, error.validator_value)
    return True


def _diff_paths(old, new, path: tuple = ()) -> set[tuple]:
    """Recursive structural diff -- returns the set of leaf paths where old
    and new differ. Dicts compared key-by-key (order-independent, as JSON
    objects should be); lists compared positionally (order matters for a
    fixed-shape array like `pillars`); a list-length change is reported at
    the list's own path rather than trying to align mismatched elements."""
    paths: set[tuple] = set()
    if isinstance(old, dict) and isinstance(new, dict):
        for key in set(old.keys()) | set(new.keys()):
            paths |= _diff_paths(old.get(key), new.get(key), path + (key,))
    elif isinstance(old, list) and isinstance(new, list):
        if len(old) != len(new):
            paths.add(path)
        else:
            for i, (o, n) in enumerate(zip(old, new)):
                paths |= _diff_paths(o, n, path + (i,))
    elif old != new:
        paths.add(path)
    return paths


def _is_authorized(path: tuple, allowed_prefixes: set[tuple]) -> bool:
    """path is authorized if it's equal to, or a descendant of, any allowed
    prefix -- e.g. a "required property missing" violation's path points at
    the containing object, not the specific field the repair adds, so
    authorization has to work by prefix, not exact match."""
    return any(path[: len(prefix)] == prefix for prefix in allowed_prefixes)


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
        return await self._parse_or_recover(
            result, full_messages, response_format, schema, schema_name, model, temperature, max_tokens,
            extra_body, allow_length_retry=True,
        )

    async def _parse_or_recover(
        self, result, full_messages, response_format, schema, schema_name, model, temperature, max_tokens,
        extra_body, *, allow_length_retry: bool,
    ) -> LLMResult:
        try:
            parsed = self._parse_and_validate(result, schema)
            return self._to_llm_result(result, parsed, model, schema_repair_attempted=False)
        except json.JSONDecodeError as exc:
            # A response that got cut off mid-generation isn't valid JSON at
            # all -- e.g. an "unterminated string". finish_reason == "length"
            # is the authoritative signal that the PROVIDER truncated it
            # (not the model emitting malformed JSON despite finishing
            # normally). Real incident this fixes: the repair path below
            # retries with the SAME max_tokens budget and asks the model to
            # regenerate the whole object again -- if the true required
            # length exceeds that budget, the repair attempt fails the exact
            # same way, producing an unrecoverable "failed twice". Retrying
            # the ORIGINAL call once with more room, before ever reaching
            # that repair path, actually addresses the cause. allow_length_
            # retry=False on the recursive call bounds this to one retry.
            finish_reason = result.choices[0].finish_reason if result.choices else None
            if allow_length_retry and finish_reason == "length":
                retried_max_tokens = int(max_tokens * _TRUNCATION_RETRY_MULTIPLIER)
                logger.info(
                    "%s response truncated at max_tokens=%d (finish_reason=length); retrying with max_tokens=%d",
                    schema_name, max_tokens, retried_max_tokens,
                )
                retried_result = await self._call_with_retry(
                    model=model, messages=full_messages, response_format=response_format,
                    temperature=temperature, max_tokens=retried_max_tokens, extra_body=extra_body,
                )
                return await self._parse_or_recover(
                    retried_result, full_messages, response_format, schema, schema_name, model, temperature,
                    max_tokens, extra_body, allow_length_retry=False,
                )
            # Not even valid JSON -- nothing to truncate-fix and no baseline
            # to diff a repair against; straight to the LLM repair fallback.
            return await self._repair_with_integrity_guard(
                full_messages, response_format, schema, schema_name, model, temperature, max_tokens,
                extra_body, error_message=str(exc), first_pass_raw=result.choices[0].message.content or "",
                first_pass_parsed=None, touched_paths=set(),
            )
        except jsonschema.ValidationError as exc:
            first_pass_raw = result.choices[0].message.content or ""
            parsed_attempt = json.loads(first_pass_raw)  # already proven valid JSON, just schema-invalid
            touched_paths: set[tuple] = set()
            current_error = exc
            for _ in range(_MAX_TRUNCATION_ITERATIONS):
                touched_paths.add(tuple(current_error.absolute_path))
                if not _apply_truncation_fix(parsed_attempt, current_error):
                    break
                try:
                    jsonschema.validate(instance=parsed_attempt, schema=schema)
                    logger.info(
                        "Fixed %s validation failure via deterministic truncation, no LLM repair needed: %s",
                        schema_name, current_error.message,
                    )
                    return self._to_llm_result(result, parsed_attempt, model, schema_repair_attempted=False)
                except jsonschema.ValidationError as next_error:
                    current_error = next_error
                    continue
            # Truncation didn't fully resolve it (a structural violation, or
            # more length violations than the iteration cap) -- fall back to
            # the LLM repair pass, against the ORIGINAL first-pass content
            # (not the partially-truncated working copy).
            return await self._repair_with_integrity_guard(
                full_messages, response_format, schema, schema_name, model, temperature, max_tokens,
                extra_body, error_message=str(current_error), first_pass_raw=first_pass_raw,
                first_pass_parsed=json.loads(first_pass_raw), touched_paths=touched_paths,
            )

    @staticmethod
    def _build_repair_prompt(error_message: str) -> str:
        # Restores spec §2's own repair-instruction clause ("change no
        # values"), strengthened -- the deployed prompt had silently dropped
        # it, which is the root cause of a real value-alteration incident
        # (repair passes rewriting untouched pillars' findings/detail text
        # wholesale, not just the field that actually violated the schema;
        # see conversation record). The prompt alone is defense-in-depth,
        # not the guarantee -- _repair_with_integrity_guard below is the
        # actual enforcement, same pattern as fda_status/coding: code-side,
        # not trust.
        return (
            "Your previous response did not validate against the required JSON schema. "
            f"Validation error: {error_message}. Correct ONLY the field(s) named in the "
            "validation error. Every other field must be returned byte-identical. Do not "
            "shorten, paraphrase, or improve any compliant content. Return ONLY corrected "
            "JSON matching the schema, with no additional commentary."
        )

    async def _repair_with_integrity_guard(
        self, full_messages, response_format, schema, schema_name, model, temperature, max_tokens,
        extra_body, *, error_message: str, first_pass_raw: str, first_pass_parsed: dict | None,
        touched_paths: set[tuple],
    ) -> LLMResult:
        """LLM repair fallback -- only reached when deterministic truncation
        either doesn't apply or couldn't fully resolve the response. After
        each repair attempt, diffs the repaired JSON against the first-pass
        JSON and rejects (and retries once, naming the violation) any change
        outside the field(s) the validation error(s) actually named. An
        honest hard error beats silently returning a rewritten assessment."""
        logger.info("Structured output failed validation for %s, attempting repair: %s", schema_name, error_message)
        assistant_content = first_pass_raw
        current_error_message = error_message
        repair_rejected = False

        for attempt in range(2):  # one repair pass, then one retry if the integrity check rejects it
            repair_messages = [
                *full_messages,
                {"role": "assistant", "content": assistant_content},
                {"role": "user", "content": self._build_repair_prompt(current_error_message)},
            ]
            repaired_response = await self._call_with_retry(
                model=model, messages=repair_messages, response_format=response_format,
                temperature=temperature, max_tokens=max_tokens, extra_body=extra_body,
            )
            try:
                repaired_parsed = self._parse_and_validate(repaired_response, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as second_exc:
                raise LLMValidationError(
                    f"Structured output for {schema_name!r} failed schema validation "
                    f"{'twice' if attempt == 0 else 'on repair retry'}: {second_exc}"
                ) from second_exc

            if first_pass_parsed is None:
                # JSONDecodeError case -- no valid baseline to diff against;
                # the integrity check structurally can't run here. Trust the
                # repair (matches prior behavior for this narrower case).
                return self._to_llm_result(
                    repaired_response, repaired_parsed, model,
                    schema_repair_attempted=True, repair_rejected=repair_rejected,
                )

            unauthorized = {p for p in _diff_paths(first_pass_parsed, repaired_parsed) if not _is_authorized(p, touched_paths)}
            if not unauthorized:
                return self._to_llm_result(
                    repaired_response, repaired_parsed, model,
                    schema_repair_attempted=True, repair_rejected=repair_rejected,
                )

            repair_rejected = True
            unauthorized_str = sorted(".".join(str(part) for part in p) for p in unauthorized)
            logger.warning(
                "Repair pass for %s altered field(s) beyond what the validation error named: %s -- %s.",
                schema_name, unauthorized_str, "retrying once" if attempt == 0 else "raising a hard error",
            )
            if attempt == 0:
                current_error_message = (
                    f"{error_message} Additionally, your previous repair attempt changed field(s) it "
                    f"should not have: {unauthorized_str}. Return corrected JSON that ONLY fixes the "
                    "originally reported violation and leaves every other field -- including the ones "
                    "you just changed -- exactly as in the ORIGINAL response below (not your previous "
                    "repair attempt)."
                )
                assistant_content = first_pass_raw  # retry from the ORIGINAL content, not the rejected repair

        raise LLMValidationError(
            f"Structured output for {schema_name!r}: repair pass altered unrelated field(s) even after "
            "being told not to -- refusing to return a silently rewritten assessment."
        )

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
        # Real incident this fixes: a rare OpenRouter/upstream-provider
        # anomaly can return a 200 OK whose parsed response has choices=None
        # (not a standard HTTP error status _call_with_retry's own handling
        # catches). Unguarded, response.choices[0] then raises a raw
        # 'NoneType' object is not subscriptable -- an unhandled TypeError,
        # not one of this app's own typed exceptions, so it surfaces to the
        # user as an unhelpful generic error instead of a clean, retryable
        # failure. Converting it to LLMProviderError here means it's caught
        # by the exact same _FAILURE_EXCEPTIONS handling every other
        # provider-level failure already goes through.
        if not response.choices:
            raise LLMProviderError(
                "OpenRouter returned no choices in its response -- this usually indicates a "
                "transient provider-side issue. Try running the scan again."
            )
        raw_content = response.choices[0].message.content or ""
        parsed = json.loads(raw_content)
        jsonschema.validate(instance=parsed, schema=schema)
        return parsed

    @staticmethod
    def _to_llm_result(
        response, parsed: dict, requested_model: str, *,
        schema_repair_attempted: bool, repair_rejected: bool = False,
    ) -> LLMResult:
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
            repair_rejected=repair_rejected,
            metadata=metadata,
        )
