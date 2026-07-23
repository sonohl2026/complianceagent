"""Structural regression test for the cost-invisibility gap found in the
status report (§2/§6): propose_llm_candidates and refine_candidates_from_
descriptions made real LLM calls with no on_usage wiring at all, so their
tokens/cost never reached token_usage_json/cost_json/metrics.

Rather than asserting specific numbers, this counts every real
structured_completion call against every on_usage invocation across the
three modules pipeline.py actually orchestrates with a shared callback
(stage1_extraction, code_candidates' fee-schedule resolution, and
stage3_synthesis). If a future LLM call is added to any of those three
without wiring on_usage, this test fails on the count mismatch rather than
silently letting a new cost-invisible call slip through.

Scope, stated plainly: this does not cover a hypothetical new stage added
directly inside pipeline.py that bypasses these three modules entirely --
it covers exactly the call sites that exist today and any new call added
within them.
"""

import pytest

from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.fee_schedule import cache
from app.services.fee_schedule.types import CodeFormat, FeeScheduleEntry
from app.services.llm.base import LLMResult
from app.services.quick_scan.code_candidates import resolve_fee_schedule_evidence
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.quick_scan.stage1_extraction import run_stage1
from app.services.quick_scan.stage3_synthesis import run_stage3

_TEST_TABLE = "test_pfs_usage_coverage"  # isolated -- see test_code_candidates.py's own note on why


@pytest.fixture(autouse=True)
async def _cleanup_test_table():
    yield
    client = cache._client()
    try:
        await client.delete(
            cache._DATA_KEY_TEMPLATE.format(table=_TEST_TABLE),
            cache._REFRESHED_AT_KEY_TEMPLATE.format(table=_TEST_TABLE),
        )
    finally:
        await client.aclose()


_VALID_STAGE3_ASSESSMENT = {
    "product": {"name": "Test Device", "manufacturer": "Test Co", "fda_status": "cleared", "identifiers": [], "dev_stage": "commercial"},
    "scores": {
        "maturity": 80, "maturity_state": "SCORED", "not_scored_reason": None,
        "assessment_coverage_pct": 100, "research_confidence": 80, "risk_flag": "LOW", "stage_context": "test.",
    },
    "pillars": [
        {"pillar": p, "status": "VERIFIED_POSITIVE", "score": 80, "finding": "f", "detail": "d", "citation": None, "gap": None, "action": "PROCEED"}
        for p in ["fda_status", "coding", "coverage", "payment", "evidence", "billing_workflow"]
    ],
    "top_gaps": [], "next_steps": [],
    "disclaimer": "Informational market-access analysis only; not legal, regulatory, or coding advice. Verify all codes and rates against official sources before billing.",
}


class _CountingLLM:
    """Answers every schema_name the real pipeline can call, and counts each
    call -- the "every provider call path" side of the assertion."""

    def __init__(self) -> None:
        self.call_count = 0

    async def structured_completion(self, **kwargs):
        self.call_count += 1
        schema_name = kwargs["schema_name"]
        if schema_name == "quick_scan_stage1":
            content = {
                "product_name": "Test Device", "manufacturer": "Test Co", "aliases": [],
                "intended_use": "AI diagnostic software for retinal analysis", "technology_type": "AI diagnostic software",
                "dev_stage_guess": "commercial", "candidate_search_terms": ["retinal analysis"],
            }
        elif schema_name in ("quick_scan_code_candidates", "quick_scan_code_refinement"):
            # Both fee-schedule calls return a real, verifiable code so
            # neither short-circuits before making its call.
            content = {"candidate_codes": ["92229"]}
        elif schema_name == "quick_scan_stage3":
            content = _VALID_STAGE3_ASSESSMENT
        else:
            raise AssertionError(f"unexpected schema_name in coverage test: {schema_name}")
        return LLMResult(
            content=content, raw_content="{}", requested_model=kwargs["model"],
            model_response_identifier="fake", prompt_tokens=10, completion_tokens=5,
            total_tokens=15, cost_usd=0.001, latency_ms=1, finish_reason="stop",
        )


class _UsageCounter:
    def __init__(self) -> None:
        self.call_count = 0
        self.stage_names: list[str] = []

    async def record(self, stage_name: str, result: LLMResult) -> None:
        self.call_count += 1
        self.stage_names.append(stage_name)


async def test_every_llm_call_across_the_pipeline_reports_usage():
    # Populate the description index so BOTH fee-schedule LLM calls fire
    # (propose_llm_candidates, then refine_candidates_from_descriptions) --
    # otherwise an empty index short-circuits the second call and this test
    # would trivially pass without ever exercising the path that was
    # previously cost-invisible.
    active = FeeScheduleEntry(
        code="92229", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs",
        payment_system="PFS", rate_usd=46.76, status_code="A", description=None,
    )
    await cache.store_table(_TEST_TABLE, {"92229": active})
    await cache.store_description_index(_TEST_TABLE, {"92229": "Img rta detc/mntr ds poc aly"})

    llm = _CountingLLM()
    usage = _UsageCounter()

    stage1 = await run_stage1(llm, "fake-model", "retinal AI diagnostic device", on_usage=usage.record)
    assert isinstance(stage1, Stage1Extraction)

    bundle = EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=False)
    evidence = await resolve_fee_schedule_evidence(llm, "fake-model", stage1, bundle, table=_TEST_TABLE, on_usage=usage.record)
    bundle.sources[evidence.source] = evidence

    await run_stage3(llm, "fake-model", stage1, bundle, on_usage=usage.record)

    # The real assertion: every real LLM call this run made was matched by
    # an on_usage call. A future call added anywhere in these three modules
    # without wiring on_usage breaks this equality.
    assert usage.call_count == llm.call_count
    # Not just equal by coincidence -- confirm all 4 expected call sites
    # actually fired (stage1, both fee-schedule calls, stage3), so this test
    # can't silently pass by both counts being 0 or 1.
    assert llm.call_count == 4
    assert usage.stage_names == [
        "stage1_extraction", "fee_schedule_llm_candidates", "fee_schedule_code_refinement", "stage3_synthesis",
    ]
