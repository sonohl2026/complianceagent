"""Stage 3: synthesis against real retrieved evidence (v2 spec §0, §2).

Loads system_prompt_v2.md VERBATIM -- plain Path.read_text(), no frontmatter
stripping, no DB/PromptVersion involvement. That mechanism
(prompts_service.get_active_master_prompt) exists so a user can upload a
replacement for the OLD pipeline's editable prompt; v2's system prompt is a
fixed, spec-mandated file the user asked to be loaded byte-for-byte, so it is
deliberately NOT routed through that versioning system.
"""

import json

from app.config import get_settings
from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import SourceEvidence
from app.services.llm.base import LLMProvider, LLMValidationError
from app.services.quick_scan.schemas import QuickScanAssessment
from app.services.quick_scan.stage1_extraction import UsageCallback, wrap_untrusted_data
from app.services.quick_scan.schemas import Stage1Extraction

_MAX_OUTPUT_TOKENS = 2000
_MAX_EVIDENCE_BLOCK_CHARS = 1500 * 4  # ~1,500 tokens at ~4 chars/token, per source


class QuickScanSynthesisError(Exception):
    """Stage-3 output failed schema validation even after the one explicit
    repair pass required by spec §2. A hard, surfaced error -- never
    silently defaulted or swallowed."""


def _read_system_prompt_v2() -> str:
    path = get_settings().prompts_path / "system_prompt_v2.md"
    return path.read_text()


def _evidence_block(evidence: SourceEvidence) -> str:
    if evidence.data is not None:
        payload = json.dumps(evidence.data, default=str)
    elif evidence.error is not None:
        payload = json.dumps({"error": evidence.error})
    else:
        payload = "{}"
    if len(payload) > _MAX_EVIDENCE_BLOCK_CHARS:
        payload = payload[:_MAX_EVIDENCE_BLOCK_CHARS]
    return f'<evidence source="{evidence.source}" status="{evidence.status.value}">\n{payload}\n</evidence>'


def build_user_message(stage1: Stage1Extraction, bundle: EvidenceBundle) -> str:
    stage1_json = stage1.model_dump_json()
    evidence_blocks = "\n".join(_evidence_block(e) for _, e in sorted(bundle.sources.items()))
    combined = f"Stage 1 extraction:\n{stage1_json}\n\nEvidence bundle:\n{evidence_blocks}"
    return wrap_untrusted_data(combined)


async def run_stage3(
    llm: LLMProvider,
    model: str,
    stage1: Stage1Extraction,
    bundle: EvidenceBundle,
    on_usage: UsageCallback | None = None,
) -> QuickScanAssessment:
    system_prompt = _read_system_prompt_v2()
    user_message = build_user_message(stage1, bundle)
    schema = QuickScanAssessment.model_json_schema()

    try:
        result = await llm.structured_completion(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            schema=schema,
            schema_name="quick_scan_stage3",
            model=model,
            temperature=0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
    except LLMValidationError as exc:
        # LLMProvider already attempts one repair retry internally (see
        # app/services/llm/base.py's LLMValidationError docstring) -- if it
        # still failed, that already IS the one repair pass spec §2 asks
        # for. Surface a hard, typed error rather than defaulting.
        raise QuickScanSynthesisError(str(exc)) from exc

    if on_usage is not None:
        await on_usage("stage3_synthesis", result)
    return QuickScanAssessment.model_validate(result.content)
