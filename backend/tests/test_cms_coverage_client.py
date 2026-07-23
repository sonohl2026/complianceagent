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


# --- qualifier-contradiction guard (Step 5 of the post-status-report work
# order): a title match on a shared substring like "continuous glucose
# monitor" doesn't weight the "implantable" qualifier that makes the policy
# inapplicable to a non-implantable device -- same general FAMILY of problem
# as the earlier Hologic openFDA false positive (a textual match accepted
# without checking whether the matched thing actually IS the target), though
# that one was a manufacturer-name substring collision fixed in
# openfda_client.py's _verify_result, a different mechanism in a different
# layer -- this guard is CMS-coverage-specific and qualifier-based. ---

_IMPLANTABLE_CGM_LISTING_BODY = {
    "meta": {"fields": ["document_id", "document_display_id", "title"], "next_token": ""},
    "data": [
        {"document_id": 38623, "document_display_id": "L38623", "title": "Implantable Continuous Glucose Monitors"},
    ],
}


@respx.mock
async def test_dexcom_g7_does_not_match_implantable_cgm_lcd():
    # The real incident: fixture 4's Dexcom G7 (external, wearable) matched
    # an LCD for implantable CGMs purely on the shared "continuous glucose
    # monitor" substring -- see run_benchmark.py's module docstring.
    respx.get(_LCD_REPORT_URL).mock(return_value=httpx.Response(200, json=_IMPLANTABLE_CGM_LISTING_BODY))
    device_context = (
        "Dexcom G7 continuous glucose monitor A small wearable sensor worn on the back of the "
        "upper arm or abdomen that measures glucose levels and sends readings to a compatible smart device."
    )
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(
            client, "lcd", ["continuous glucose monitor"], device_context=device_context,
        )
    assert result.status == RetrievalStatus.MISS
    assert result.data["reason"] == "qualifier_contradiction"
    assert "Implantable Continuous Glucose Monitors" in result.data["excluded_titles"]


@respx.mock
async def test_qualifier_guard_generalizes_beyond_implantable_pair():
    # A second, distinct qualifier pair (pediatric/adult) -- confirms the
    # guard isn't a one-off special case for CGMs specifically.
    listing = {
        "meta": {"fields": ["document_id", "title"], "next_token": ""},
        "data": [{"document_id": 1, "title": "Pediatric Cochlear Implant Devices"}],
    }
    respx.get(_LCD_REPORT_URL).mock(return_value=httpx.Response(200, json=listing))
    device_context = "Acme CI-9000 cochlear implant intended for adult patients with severe hearing loss."
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(
            client, "lcd", ["cochlear implant"], device_context=device_context,
        )
    assert result.status == RetrievalStatus.MISS
    assert result.data["reason"] == "qualifier_contradiction"


@respx.mock
async def test_qualifier_guard_does_not_reject_a_genuinely_matching_title():
    # Same device text, but the title carries no contradicting qualifier --
    # must still HIT normally. Guards against the guard itself being too
    # aggressive.
    respx.get(_NCD_REPORT_URL).mock(return_value=httpx.Response(200, json=_NCD_LISTING_BODY))
    device_context = "Edwards SAPIEN 3 transcatheter aortic valve, a PMA-approved implant."
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(
            client, "ncd", ["transcatheter aortic valve"], device_context=device_context,
        )
    assert result.status == RetrievalStatus.HIT
    assert result.data["matches"][0]["document_display_id"] == "20.32"


@respx.mock
async def test_qualifier_guard_skips_ambiguous_device_text_mentioning_both_sides():
    # If the device's own text mentions BOTH sides of a pair (e.g. a device
    # usable unilaterally or bilaterally), that's ambiguous, not a clean
    # contradiction -- must not be excluded.
    listing = {
        "meta": {"fields": ["document_id", "title"], "next_token": ""},
        "data": [{"document_id": 1, "title": "Unilateral Cochlear Implant Devices"}],
    }
    respx.get(_LCD_REPORT_URL).mock(return_value=httpx.Response(200, json=listing))
    device_context = "Acme CI-9000 cochlear implant, indicated for unilateral or bilateral implantation."
    async with httpx.AsyncClient() as client:
        result = await cms_coverage_client.search_unlicensed(
            client, "lcd", ["cochlear implant"], device_context=device_context,
        )
    assert result.status == RetrievalStatus.HIT


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
