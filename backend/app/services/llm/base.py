"""LLM provider abstraction (build spec §9.1).

Kept intentionally narrow: one method the analysis pipeline actually needs
(structured, schema-validated JSON output). A local OpenAI-compatible server
or Ollama adapter can implement this same interface later without the
pipeline code changing.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class LLMResult:
    content: dict
    raw_content: str
    requested_model: str
    model_response_identifier: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None
    latency_ms: int
    finish_reason: str | None
    schema_repair_attempted: bool = False
    metadata: dict = field(default_factory=dict)


class LLMValidationError(Exception):
    """Structured output failed schema validation even after one repair retry."""


class LLMProviderError(Exception):
    """Non-retryable provider error (auth failure, bad request, no model configured)."""


class LLMProvider(Protocol):
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
    ) -> LLMResult: ...
