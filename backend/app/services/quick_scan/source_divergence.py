"""Multi-source divergence check (only relevant when 2+ sources are
attached in one submission -- see quick_scans.py::start_quick_scan). Real
incident this addresses: attaching sources about two different devices in
one submission (e.g. one device's web link plus a different device's
academic paper) silently blended into one confused analysis, since Stage 1
extraction only ever produces ONE product identity from whatever text it's
given.

Uses the same "let the LLM reason over real, structured input" pattern
already proven for the billing-code relevance gate (code_candidates.py) --
a single LLM call given each source's own (truncated) text, asked only
whether they describe the same product or different ones, not a fragile
name-similarity/keyword heuristic.
"""

from app.services.analysis.prompts_service import load_module_prompt
from app.services.llm.base import LLMProvider, LLMResult
from app.services.quick_scan.schemas import SourceDivergenceCheck
from app.services.quick_scan.stage1_extraction import UsageCallback, wrap_untrusted_data

_MAX_OUTPUT_TOKENS = 800  # small, fixed-shape output (product identities + index groupings)
_MAX_CHARS_PER_SOURCE = 2000  # just enough to identify the product, not the full per-source budget
# used later by the real Stage 1 extraction once a product is chosen.


def _build_sources_block(source_texts: list[str]) -> str:
    excerpts = "\n\n".join(
        f"--- Source {i} ---\n{text[:_MAX_CHARS_PER_SOURCE]}" for i, text in enumerate(source_texts)
    )
    return wrap_untrusted_data(excerpts)


async def check_source_divergence(
    llm: LLMProvider, model: str, source_texts: list[str], on_usage: UsageCallback | None = None
) -> SourceDivergenceCheck:
    module_prompt = load_module_prompt("quick_scan_source_divergence")
    user_message = _build_sources_block(source_texts)
    schema = SourceDivergenceCheck.model_json_schema()

    result: LLMResult = await llm.structured_completion(
        system_prompt=module_prompt, messages=[{"role": "user", "content": user_message}],
        schema=schema, schema_name="quick_scan_source_divergence", model=model,
        temperature=0, max_tokens=_MAX_OUTPUT_TOKENS,
    )
    if on_usage is not None:
        await on_usage("source_divergence_check", result)
    return SourceDivergenceCheck.model_validate(result.content)
