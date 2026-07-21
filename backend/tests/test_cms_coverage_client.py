import httpx
import respx

from app.services.evidence_retrieval import cms_coverage_client
from app.services.evidence_retrieval.types import RetrievalStatus

_NCD_REPORT_URL = "https://api.coverage.cms.gov/v1/reports/national-coverage-ncd"
_LCD_REPORT_URL = "https://api.coverage.cms.gov/v1/reports/local-coverage-final-lcds"
_LCD_DETAIL_URL = "https://api.coverage.cms.gov/v1/data/lcd"
_LICENSE_URL = "https://api.coverage.cms.gov/v1/metadata/license-agreement/"

# Real (trimmed) response shapes, verified against the live API before writing this test.
_NCD_LISTING_BODY = {
    "meta": {"fields": ["document_id", "document_display_id", "title"], "next_token": ""},
    "data": [
        {"document_id": 108, "document_display_id": "100.3", "title": "24-Hour Ambulatory Esophageal pH Monitoring"},
        {"document_id": 200, "document_display_id": "20.32", "title": "Transcatheter Aortic Valve Replacement (TAVR)"},
    ],
}


def setup_function():
    # Module-level caches (listing + token) must not leak between tests.
    cms_coverage_client._listing_cache.clear()
    cms_coverage_client._token_cache.clear()


@respx.mock
async def test_search_unlicensed_matches_title_case_insensitively():
    respx.get(_NCD_REPORT_URL).mock(return_value=httpx.Response(200, json=_NCD_LISTING_BODY))
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(client, "ncd", ["transcatheter aortic valve"])
    assert result.status == RetrievalStatus.HIT
    assert result.data["matches"][0]["document_display_id"] == "20.32"


@respx.mock
async def test_search_unlicensed_no_match_is_miss():
    respx.get(_NCD_REPORT_URL).mock(return_value=httpx.Response(200, json=_NCD_LISTING_BODY))
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(client, "ncd", ["completely unrelated condition"])
    assert result.status == RetrievalStatus.MISS


@respx.mock
async def test_listing_is_cached_across_calls():
    route = respx.get(_NCD_REPORT_URL).mock(return_value=httpx.Response(200, json=_NCD_LISTING_BODY))
    async with httpx.AsyncClient() as client:
        await cms_coverage_client.search_unlicensed(client, "ncd", ["tavr"])
        await cms_coverage_client.search_unlicensed(client, "ncd", ["esophageal"])
    # Second call must reuse the cached listing, not re-fetch ~1MB again.
    assert route.call_count == 1


@respx.mock
async def test_listing_retrieval_failure_propagates_as_such():
    respx.get(_LCD_REPORT_URL).mock(side_effect=httpx.TimeoutException("simulated"))
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(client, "lcd", ["glucose"])
    assert result.status == RetrievalStatus.RETRIEVAL_FAILURE


@respx.mock
async def test_licensed_document_not_fetched_when_toggle_off():
    license_route = respx.get(_LICENSE_URL).mock(return_value=httpx.Response(200, json={"data": [{"Token": "unused"}]}))
    detail_route = respx.get(_LCD_DETAIL_URL).mock(return_value=httpx.Response(200, json={"data": [{"title": "should not be reached"}]}))
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.get_licensed_document(
            client, "lcd", "33822", "1", settings={"cms_license_accepted": False},
        )
    assert result.status == RetrievalStatus.MISS
    assert result.data["reason"] == "cms_license_not_accepted"
    assert license_route.call_count == 0  # never even attempted
    assert detail_route.call_count == 0


@respx.mock
async def test_licensed_document_fetches_token_and_document_when_toggle_on():
    respx.get(_LICENSE_URL).mock(return_value=httpx.Response(200, json={"data": [{"Token": "real-token-abc"}]}))
    detail_route = respx.get(_LCD_DETAIL_URL).mock(
        return_value=httpx.Response(200, json={"data": [{"title": "Continuous Glucose Monitoring LCD"}]})
    )
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.get_licensed_document(
            client, "lcd", "33822", "1", settings={"cms_license_accepted": True},
        )
    assert result.status == RetrievalStatus.HIT
    assert result.data["document"]["title"] == "Continuous Glucose Monitoring LCD"
    sent_auth_header = detail_route.calls.last.request.headers["authorization"]
    assert sent_auth_header == "Bearer real-token-abc"


@respx.mock
async def test_token_refreshed_on_401():
    respx.get(_LICENSE_URL).mock(
        side_effect=[
            httpx.Response(200, json={"data": [{"Token": "stale-token"}]}),
            httpx.Response(200, json={"data": [{"Token": "fresh-token"}]}),
        ]
    )
    detail_route = respx.get(_LCD_DETAIL_URL).mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"data": [{"title": "found after refresh"}]}),
        ]
    )
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.get_licensed_document(
            client, "lcd", "33822", "1", settings={"cms_license_accepted": True},
        )
    assert result.status == RetrievalStatus.HIT
    assert detail_route.call_count == 2
    assert detail_route.calls[0].request.headers["authorization"] == "Bearer stale-token"
    assert detail_route.calls[1].request.headers["authorization"] == "Bearer fresh-token"
