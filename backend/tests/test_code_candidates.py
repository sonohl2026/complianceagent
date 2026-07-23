import pytest

from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.fee_schedule import cache
from app.services.fee_schedule.types import CodeFormat, FeeScheduleEntry
from app.services.quick_scan.code_candidates import (
    extract_code_mentions,
    refine_candidates_from_descriptions,
    resolve_fee_schedule_evidence,
    verify_candidates,
)
from app.services.quick_scan.schemas import Stage1Extraction


def _stage1(**overrides) -> Stage1Extraction:
    defaults = dict(
        product_name="Test Device", manufacturer="Test Co", aliases=[], intended_use="testing",
        technology_type="diagnostic ultrasound", dev_stage_guess="commercial", candidate_search_terms=[],
    )
    defaults.update(overrides)
    return Stage1Extraction(**defaults)


class _FakeCandidateLLM:
    def __init__(self, candidate_codes, refinement_codes=None):
        self.candidate_codes = candidate_codes
        # Lets one fake instance simulate "memorized-knowledge call proposes
        # nothing, but the real-data-grounded refinement call picks
        # correctly" -- the exact failure mode this whole mechanism fixes.
        self.refinement_codes = refinement_codes if refinement_codes is not None else candidate_codes

    async def structured_completion(self, **kwargs):
        from app.services.llm.base import LLMResult
        codes = self.refinement_codes if kwargs["schema_name"] == "quick_scan_code_refinement" else self.candidate_codes
        return LLMResult(
            content={"candidate_codes": codes}, raw_content="{}", requested_model=kwargs["model"],
            model_response_identifier="fake", prompt_tokens=0, completion_tokens=0,
            total_tokens=0, cost_usd=0.0, latency_ms=1, finish_reason="stop",
        )


def test_extract_code_mentions_finds_valid_shapes_only():
    text = "Bill under CPT 76705 or HCPCS A4238. See page 12345 of the manual, dated 2026."
    mentions = extract_code_mentions(text)
    assert "76705" in mentions
    assert "A4238" in mentions
    # "12345" is a plausible-shaped 5-digit token too (that's expected --
    # verification against real fee-schedule data is what filters it out,
    # not this extraction step).


def test_extract_code_mentions_empty_text():
    assert extract_code_mentions("") == []
    assert extract_code_mentions(None) == []


# Deliberately NOT "pfs" -- that's the real production table name. Using an
# isolated name here is defense-in-depth on top of cache.py's own db-index
# isolation (PYTEST_CURRENT_TEST routes every test to a separate Redis
# database), not a substitute for it -- see the real incident this fixes in
# cache.py's module docstring: a test that reused "pfs" for throwaway data
# and deleted it in teardown silently wiped the real cached fee-schedule
# data on every test run.
_TEST_TABLE = "test_pfs_candidates"


@pytest.fixture(autouse=True)
async def _cleanup_test_table():
    yield
    client = cache._client()
    try:
        await client.delete(cache._DATA_KEY_TEMPLATE.format(table=_TEST_TABLE), cache._REFRESHED_AT_KEY_TEMPLATE.format(table=_TEST_TABLE))
    finally:
        await client.aclose()


async def test_verify_candidates_keeps_only_active_verified_codes():
    active = FeeScheduleEntry(code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None)
    inactive = FeeScheduleEntry(code="A4238", code_format=CodeFormat.HCPCS_LEVEL_II, active=False, source="pfs", payment_system="PFS", rate_usd=None, status_code="X", description="Adju cgm supply allowance")
    await cache.store_table(_TEST_TABLE, {"76705": active, "A4238": inactive})

    verified = await verify_candidates(["76705", "A4238", "99999", "not-a-code"], table=_TEST_TABLE)
    assert [e.code for e in verified] == ["76705"]  # inactive and nonexistent codes both dropped


async def test_verify_candidates_deduplicates():
    active = FeeScheduleEntry(code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None)
    await cache.store_table(_TEST_TABLE, {"76705": active})
    verified = await verify_candidates(["76705", "76705", "76705"], table=_TEST_TABLE)
    assert len(verified) == 1


async def test_resolve_fee_schedule_evidence_hit_when_llm_candidate_verifies():
    active = FeeScheduleEntry(code="76705", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=86.17, status_code="A", description=None)
    await cache.store_table(_TEST_TABLE, {"76705": active})

    bundle = EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=False)
    llm = _FakeCandidateLLM(["76705"])
    evidence = await resolve_fee_schedule_evidence(llm, "fake-model", _stage1(), bundle, table=_TEST_TABLE)
    assert evidence.status == RetrievalStatus.HIT
    assert evidence.data["verified_codes"][0]["code"] == "76705"
    assert evidence.data["verified_codes"][0]["description"] is None  # CPT format -- never shown


async def test_resolve_fee_schedule_evidence_miss_when_nothing_verifies():
    bundle = EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=False)
    llm = _FakeCandidateLLM(["00000"])  # not in the (empty) test table
    evidence = await resolve_fee_schedule_evidence(llm, "fake-model", _stage1(), bundle, table=_TEST_TABLE)
    assert evidence.status == RetrievalStatus.MISS


async def test_resolve_fee_schedule_evidence_uses_sourced_hints_from_cms_detail():
    active = FeeScheduleEntry(code="93000", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=15.36, status_code="A", description=None)
    await cache.store_table(_TEST_TABLE, {"93000": active})

    bundle = EvidenceBundle(
        sources={
            "cms_article_detail": SourceEvidence(
                source="cms_article_detail", status=RetrievalStatus.HIT, latency_ms=0,
                data={"document": {"description": "Bill under CPT 93000 for this service."}},
            ),
        },
        all_openfda_failed=False, all_cms_failed=False,
    )
    llm = _FakeCandidateLLM([])  # LLM proposes nothing -- the sourced hint alone should still verify
    evidence = await resolve_fee_schedule_evidence(llm, "fake-model", _stage1(), bundle, table=_TEST_TABLE)
    assert evidence.status == RetrievalStatus.HIT
    assert evidence.data["verified_codes"][0]["code"] == "93000"


# --- description-index-driven refinement (fixes the confirmed LLM knowledge
# gap: asked directly, the model gave a confidently WRONG definition for a
# real, current CPT code rather than admitting it didn't know) ---

async def test_refine_candidates_filters_to_only_shown_codes():
    # Never trust the model to only echo codes it was actually shown.
    llm = _FakeCandidateLLM([], refinement_codes=["92229", "99999-not-shown"])
    picked = await refine_candidates_from_descriptions(
        llm, "fake-model", _stage1(), {"92229": "Img rta detc/mntr ds poc aly"},
    )
    assert picked == ["92229"]


async def test_refine_candidates_empty_input_short_circuits_without_llm_call():
    class _ExplodingLLM:
        async def structured_completion(self, **kwargs):
            raise AssertionError("should never be called with no candidates")

    picked = await refine_candidates_from_descriptions(_ExplodingLLM(), "fake-model", _stage1(), {})
    assert picked == []


async def test_resolve_fee_schedule_evidence_finds_code_via_description_index_when_llm_memory_fails():
    # The exact real-world case this fixes: propose_llm_candidates (memory)
    # proposes nothing useful, but the real PFS description ("Img rta
    # detc/mntr ds poc aly") textually matches the device's own intended_use,
    # and the refinement call correctly picks it once shown real data.
    active = FeeScheduleEntry(code="92229", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=46.76, status_code="A", description=None)
    await cache.store_table(_TEST_TABLE, {"92229": active})
    await cache.store_description_index(_TEST_TABLE, {"92229": "Img rta detc/mntr ds poc aly"})

    stage1 = _stage1(
        technology_type="AI diagnostic software",
        intended_use="Analyzes retinal images to detect more than mild diabetic retinopathy without requiring a clinician to interpret the image in primary care settings.",
    )
    bundle = EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=False)
    llm = _FakeCandidateLLM([], refinement_codes=["92229"])  # memory call proposes nothing; refinement finds it
    evidence = await resolve_fee_schedule_evidence(llm, "fake-model", stage1, bundle, table=_TEST_TABLE)
    assert evidence.status == RetrievalStatus.HIT
    assert evidence.data["verified_codes"][0]["code"] == "92229"


async def test_raw_cpt_description_never_leaks_into_evidence_output():
    # The AMA-license boundary, proven end to end: even though the raw,
    # AMA-licensed description text is used as input to the internal
    # refinement call, it must never appear anywhere in what this function
    # returns (which flows into Stage 3's evidence bundle).
    raw_description = "Img rta detc/mntr ds poc aly"
    active = FeeScheduleEntry(code="92229", code_format=CodeFormat.CPT_CATEGORY_I, active=True, source="pfs", payment_system="PFS", rate_usd=46.76, status_code="A", description=None)
    await cache.store_table(_TEST_TABLE, {"92229": active})
    await cache.store_description_index(_TEST_TABLE, {"92229": raw_description})

    stage1 = _stage1(technology_type="AI diagnostic software", intended_use="autonomous retinal analysis")
    bundle = EvidenceBundle(sources={}, all_openfda_failed=False, all_cms_failed=False)
    llm = _FakeCandidateLLM([], refinement_codes=["92229"])
    evidence = await resolve_fee_schedule_evidence(llm, "fake-model", stage1, bundle, table=_TEST_TABLE)

    serialized = str(evidence.data)
    assert raw_description not in serialized
    assert "poc aly" not in serialized  # no fragment of the raw descriptor either
    assert evidence.data["verified_codes"][0]["description"] is None
