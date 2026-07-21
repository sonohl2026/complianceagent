import httpx
import respx

from app.services.evidence_retrieval import cms_coverage_client
from app.services.evidence_retrieval.orchestrator import run_evidence_retrieval
from app.services.evidence_retrieval.types import RetrievalStatus


class _FakeStage1:
    def __init__(self, product_name="Dexcom G7", manufacturer="Dexcom", aliases=None, candidate_search_terms=None):
        self.product_name = product_name
        self.manufacturer = manufacturer
        self.aliases = aliases or []
        self.candidate_search_terms = candidate_search_terms or ["continuous glucose monitor"]


def setup_function():
    cms_coverage_client._listing_cache.clear()
    cms_coverage_client._token_cache.clear()


@respx.mock
async def test_orchestrator_gathers_all_sources_concurrently():
    respx.get(url__regex=r"https://api\.fda\.gov/device/.*").mock(
        return_value=httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
    )
    respx.get(url__regex=r"https://api\.coverage\.cms\.gov/v1/reports/.*").mock(
        return_value=httpx.Response(200, json={"meta": {}, "data": []})
    )
    bundle = await run_evidence_retrieval(_FakeStage1())
    # 7 openFDA endpoints + 3 CMS resources
    assert len(bundle.sources) == 10
    assert all(e.status == RetrievalStatus.MISS for e in bundle.sources.values())
    assert bundle.force_not_scored is False  # MISS is not failure


@respx.mock
async def test_both_sources_fully_failing_forces_not_scored():
    respx.get(url__regex=r"https://api\.fda\.gov/device/.*").mock(side_effect=httpx.TimeoutException("down"))
    respx.get(url__regex=r"https://api\.coverage\.cms\.gov/v1/reports/.*").mock(side_effect=httpx.TimeoutException("down"))
    bundle = await run_evidence_retrieval(_FakeStage1())
    assert bundle.all_openfda_failed is True
    assert bundle.all_cms_failed is True
    assert bundle.force_not_scored is True


@respx.mock
async def test_partial_failure_does_not_force_not_scored():
    respx.get(url__regex=r"https://api\.fda\.gov/device/.*").mock(
        return_value=httpx.Response(200, json={"results": [{"device_name": "Dexcom G7"}]})
    )
    respx.get(url__regex=r"https://api\.coverage\.cms\.gov/v1/reports/.*").mock(side_effect=httpx.TimeoutException("down"))
    bundle = await run_evidence_retrieval(_FakeStage1())
    assert bundle.all_openfda_failed is False
    assert bundle.all_cms_failed is True
    assert bundle.force_not_scored is False  # only one side failed entirely


@respx.mock
async def test_progress_callback_invoked_per_source():
    respx.get(url__regex=r"https://api\.fda\.gov/device/.*").mock(
        return_value=httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
    )
    respx.get(url__regex=r"https://api\.coverage\.cms\.gov/v1/reports/.*").mock(
        return_value=httpx.Response(200, json={"meta": {}, "data": []})
    )
    seen: list[str] = []

    async def on_progress(source_name, evidence):
        seen.append(source_name)

    await run_evidence_retrieval(_FakeStage1(), on_progress=on_progress)
    assert len(seen) == 10
    assert len(set(seen)) == 10  # each source reported exactly once
