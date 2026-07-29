import pytest

from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.llm.base import LLMResult, LLMValidationError
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.quick_scan.stage3_synthesis import (
    QuickScanSynthesisError,
    build_user_message,
    run_stage3,
)


class _FakeLLMProvider:
    def __init__(self, content: dict | None = None, raise_validation_error: bool = False):
        self.content = content
        self.raise_validation_error = raise_validation_error
        self.last_call_kwargs: dict | None = None

    async def structured_completion(self, **kwargs) -> LLMResult:
        self.last_call_kwargs = kwargs
        if self.raise_validation_error:
            raise LLMValidationError("simulated: schema repair also failed")
        return LLMResult(
            content=self.content, raw_content="{}", requested_model=kwargs["model"],
            model_response_identifier="fake-1", prompt_tokens=500, completion_tokens=300,
            total_tokens=800, cost_usd=0.001, latency_ms=20, finish_reason="stop",
        )


def _stage1() -> Stage1Extraction:
    return Stage1Extraction(
        product_name="Dexcom G7", manufacturer="Dexcom", aliases=[], intended_use="CGM",
        technology_type="continuous glucose monitor", dev_stage_guess="commercial",
        candidate_search_terms=["continuous glucose monitor"],
    )


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        sources={
            "openfda_510k": SourceEvidence(source="openfda_510k", status=RetrievalStatus.HIT, latency_ms=100, data={"results": [{"k_number": "K123"}]}),
            "cms_ncd": SourceEvidence(source="cms_ncd", status=RetrievalStatus.MISS, latency_ms=50),
        },
        all_openfda_failed=False, all_cms_failed=False,
    )


_VALID_ASSESSMENT = {
    "product": {"name": "Dexcom G7", "manufacturer": "Dexcom", "fda_status": "cleared", "identifiers": [], "dev_stage": "commercial"},
    "scores": {
        "maturity": 85, "maturity_state": "SCORED", "not_scored_reason": None,
        "assessment_coverage_pct": 50, "research_confidence": 80, "risk_flag": "LOW", "stage_context": "Mature, on-track.",
    },
    "pillars": [
        {"pillar": p, "status": "UNKNOWN", "score": None, "finding": "f", "detail": "d", "citation": None, "gap": None, "action": None}
        for p in ["fda_status", "coding", "coverage", "payment", "evidence", "billing_workflow"]
    ],
    "top_gaps": [], "next_steps": [],
    "disclaimer": "Informational market-access analysis only; not legal, regulatory, or coding advice. Verify all codes and rates against official sources before billing.",
}


async def test_run_stage3_returns_validated_assessment():
    fake_llm = _FakeLLMProvider(content=_VALID_ASSESSMENT)
    result = await run_stage3(fake_llm, "strong/model", _stage1(), _bundle())
    assert result.product.name == "Dexcom G7"
    assert result.scores.maturity == 85


async def test_run_stage3_loads_system_prompt_v2_verbatim():
    fake_llm = _FakeLLMProvider(content=_VALID_ASSESSMENT)
    await run_stage3(fake_llm, "model", _stage1(), _bundle())
    system_prompt = fake_llm.last_call_kwargs["system_prompt"]
    assert "You are a US medical-device market-access analyst" in system_prompt
    assert "You are NOT a document grader" in system_prompt
    assert "Informational market-access analysis only" in system_prompt


async def test_run_stage3_uses_3500_max_tokens():
    fake_llm = _FakeLLMProvider(content=_VALID_ASSESSMENT)
    await run_stage3(fake_llm, "model", _stage1(), _bundle())
    assert fake_llm.last_call_kwargs["max_tokens"] == 3500


async def test_run_stage3_raises_typed_error_when_repair_also_fails():
    fake_llm = _FakeLLMProvider(raise_validation_error=True)
    with pytest.raises(QuickScanSynthesisError):
        await run_stage3(fake_llm, "model", _stage1(), _bundle())


def test_build_user_message_tags_each_source_with_status():
    message = build_user_message(_stage1(), _bundle())
    assert '<evidence source="openfda_510k" status="HIT">' in message
    assert '<evidence source="cms_ncd" status="MISS">' in message
    assert message.startswith("<untrusted_data>")
    assert "Dexcom G7" in message


# --- uploaded document reaching Stage 3 (added after finding the pipeline
# previously discarded it entirely post-Stage-1 -- see conversation record) ---

def test_build_user_message_includes_uploaded_document_block_when_present():
    message = build_user_message(_stage1(), _bundle(), source_text="Pivotal trial: sensitivity 87%, specificity 91%.")
    assert "<uploaded_document>" in message
    assert "</uploaded_document>" in message
    assert "sensitivity 87%" in message
    # Still a genuinely separate block from evidence sources -- never
    # tagged with a HIT/MISS/RETRIEVAL_FAILURE status like a real source.
    assert '<uploaded_document status=' not in message


def test_build_user_message_omits_uploaded_document_block_when_absent():
    message = build_user_message(_stage1(), _bundle(), source_text=None)
    assert "<uploaded_document>" not in message
    message_empty = build_user_message(_stage1(), _bundle(), source_text="   ")
    assert "<uploaded_document>" not in message_empty


def test_build_user_message_truncates_very_long_uploaded_document():
    from app.services.quick_scan.stage3_synthesis import _MAX_UPLOADED_DOCUMENT_CHARS
    long_text = "x" * (_MAX_UPLOADED_DOCUMENT_CHARS + 5000)
    message = build_user_message(_stage1(), _bundle(), source_text=long_text)
    # +len("<uploaded_document>\n") etc. -- just confirm it's bounded, not
    # that the whole 5000-char excess made it through.
    assert len(message) < len(long_text) + 2000


async def test_run_stage3_passes_source_text_through_to_the_llm_call():
    fake_llm = _FakeLLMProvider(content=_VALID_ASSESSMENT)
    await run_stage3(fake_llm, "model", _stage1(), _bundle(), source_text="Pivotal trial data here.")
    user_message = fake_llm.last_call_kwargs["messages"][0]["content"]
    assert "Pivotal trial data here." in user_message
