from unittest.mock import AsyncMock, MagicMock

from app.services.evidence_retrieval.orchestrator import EvidenceBundle
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence
from app.services.quick_scan import pipeline
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.web_search.brave_client import BraveSearchError, WebSearchResult


def _stage1(name="Widget X1", aliases=None, search_terms=None):
    return Stage1Extraction(
        product_name=name, manufacturer="Acme", aliases=aliases or [],
        intended_use="widgeting", technology_type="widget", dev_stage_guess="commercial",
        candidate_search_terms=search_terms or [name],
    )


def test_apply_name_hint_overrides_extracted_name_and_keeps_it_as_alias():
    stage1 = _stage1(name="Widget X1", search_terms=["widget"])
    updated = pipeline._apply_name_hint(stage1, "Acme SuperWidget")
    assert updated.product_name == "Acme SuperWidget"
    assert "Widget X1" in updated.aliases
    assert updated.candidate_search_terms[0] == "Acme SuperWidget"


def test_apply_name_hint_matching_extracted_name_is_a_no_op():
    stage1 = _stage1(name="Widget X1")
    updated = pipeline._apply_name_hint(stage1, "widget x1")
    assert updated is stage1


def test_apply_name_hint_blank_hint_is_a_no_op():
    stage1 = _stage1(name="Widget X1")
    updated = pipeline._apply_name_hint(stage1, "   ")
    assert updated is stage1


def test_seed_stage1_from_name_has_no_material_and_searches_on_the_name():
    stage1 = pipeline._seed_stage1_from_name("Acme Widget")
    assert stage1.product_name == "Acme Widget"
    assert stage1.manufacturer == ""
    assert stage1.candidate_search_terms == ["Acme Widget"]


class _FakeLLM:
    async def structured_completion(self, **kwargs):
        raise AssertionError("Name-only identity resolution must never call Stage 1/an LLM directly")


async def _run_identity_resolution(
    monkeypatch, bundle: EvidenceBundle, product_name: str = "Acme Widget", settings: dict | None = None,
):
    async def fake_retrieval(stage1, on_progress=None, settings=None):
        assert stage1.product_name == product_name
        if on_progress:
            for source_name, evidence in bundle.sources.items():
                await on_progress(source_name, evidence)
        return bundle

    async def fake_fee_schedule(llm, model, stage1, evidence_bundle, on_usage):
        return

    monkeypatch.setattr(pipeline, "run_evidence_retrieval", fake_retrieval)
    monkeypatch.setattr(pipeline, "_add_fee_schedule_evidence", fake_fee_schedule)
    monkeypatch.setattr(pipeline, "load_runtime_settings", lambda: settings or {})

    analysis_run = MagicMock()
    analysis_run.retrieval_progress_json = {}
    db = AsyncMock()

    identity_found = await pipeline.run_quick_scan_identity_resolution(
        db, analysis_run, _FakeLLM(), "some/model", product_name
    )
    return identity_found, analysis_run


async def test_identity_resolution_pauses_for_confirmation_on_a_hit(monkeypatch):
    bundle = EvidenceBundle(
        sources={
            "openfda_510k": SourceEvidence(
                source="openfda_510k", status=RetrievalStatus.HIT, latency_ms=5,
                data={"k_number": "K123456"}, match_confidence="exact",
            ),
        },
        all_openfda_failed=False, all_cms_failed=False,
    )
    identity_found, analysis_run = await _run_identity_resolution(monkeypatch, bundle)

    assert identity_found is True
    assert analysis_run.current_stage == "awaiting_confirmation"
    assert analysis_run.retrieval_bundle_json["stage1"]["product_name"] == "Acme Widget"
    assert "openfda_510k" in analysis_run.retrieval_bundle_json["sources"]


async def test_identity_resolution_reports_no_hit_when_nothing_found(monkeypatch):
    bundle = EvidenceBundle(
        sources={
            "openfda_510k": SourceEvidence(source="openfda_510k", status=RetrievalStatus.MISS, latency_ms=5),
        },
        all_openfda_failed=False, all_cms_failed=False,
    )
    identity_found, analysis_run = await _run_identity_resolution(
        monkeypatch, bundle, product_name="Nonexistent Gadget 9000"
    )

    assert identity_found is False
    assert analysis_run.current_stage == "awaiting_confirmation"
    assert "candidate_site" not in analysis_run.retrieval_bundle_json  # no API key configured in this test


_MISS_BUNDLE = EvidenceBundle(
    sources={"openfda_510k": SourceEvidence(source="openfda_510k", status=RetrievalStatus.MISS, latency_ms=5)},
    all_openfda_failed=False, all_cms_failed=False,
)


async def test_identity_resolution_offers_candidate_site_on_a_zero_hit(monkeypatch):
    async def fake_search(query, api_key, count=1):
        assert query == "Nonexistent Gadget 9000"
        assert api_key == "brave-key"
        return [WebSearchResult(title="Gadget Co", url="https://example.com/gadget", snippet="The real gadget.")]

    monkeypatch.setattr(pipeline, "brave_search", fake_search)
    identity_found, analysis_run = await _run_identity_resolution(
        monkeypatch, _MISS_BUNDLE, product_name="Nonexistent Gadget 9000",
        settings={"brave_search_api_key": "brave-key"},
    )

    assert identity_found is False
    assert analysis_run.retrieval_bundle_json["candidate_site"] == {
        "title": "Gadget Co", "url": "https://example.com/gadget", "snippet": "The real gadget.",
    }


async def test_identity_resolution_skips_search_without_an_api_key(monkeypatch):
    async def fake_search(query, api_key, count=1):
        raise AssertionError("must not search without a configured API key")

    monkeypatch.setattr(pipeline, "brave_search", fake_search)
    identity_found, analysis_run = await _run_identity_resolution(
        monkeypatch, _MISS_BUNDLE, product_name="Nonexistent Gadget 9000", settings={},
    )

    assert identity_found is False
    assert "candidate_site" not in analysis_run.retrieval_bundle_json


async def test_identity_resolution_tolerates_a_search_provider_failure(monkeypatch):
    async def fake_search(query, api_key, count=1):
        raise BraveSearchError("rate limited")

    monkeypatch.setattr(pipeline, "brave_search", fake_search)
    identity_found, analysis_run = await _run_identity_resolution(
        monkeypatch, _MISS_BUNDLE, product_name="Nonexistent Gadget 9000",
        settings={"brave_search_api_key": "brave-key"},
    )

    assert identity_found is False
    assert "candidate_site" not in analysis_run.retrieval_bundle_json
