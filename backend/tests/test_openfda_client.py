import httpx
import respx

from app.services.evidence_retrieval import openfda_client
from app.services.evidence_retrieval.types import RetrievalStatus

_510K_URL = "https://api.fda.gov/device/510k.json"
_CLASSIFICATION_URL = "https://api.fda.gov/device/classification.json"


@respx.mock
async def test_search_hits_real_shaped_response_for_lumineticscore():
    # Real openFDA response shape for a De Novo AI diagnostic (LumineticsCore/IDx-DR)
    respx.get(_510K_URL).mock(
        return_value=httpx.Response(200, json={
            "meta": {"results": {"total": 1}},
            "results": [{"device_name": "IDx-DR", "applicant": "Digital Diagnostics Inc.", "k_number": "K192371"}],
        })
    )
    async with httpx.AsyncClient() as client:
        result = await openfda_client.search_510k(
            client, product_name="IDx-DR", manufacturer="Digital Diagnostics", aliases=["LumineticsCore"],
        )
    assert result.status == RetrievalStatus.HIT
    assert result.data["results"][0]["k_number"] == "K192371"
    assert result.match_confidence == "exact"


@respx.mock
async def test_search_falls_back_through_manufacturer_then_aliases():
    route = respx.get(_510K_URL).mock(
        side_effect=[
            httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}}),
            httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}}),
            httpx.Response(200, json={"results": [{"device_name": "matched via alias"}]}),
        ]
    )
    async with httpx.AsyncClient() as client:
        result = await openfda_client.search_510k(
            client, product_name="Unmatched Exact Name", manufacturer="Unmatched Mfr", aliases=["Real Alias"],
        )
    assert result.status == RetrievalStatus.HIT
    assert result.match_confidence == "uncertain"
    assert route.call_count == 3


@respx.mock
async def test_genuine_no_match_is_miss_not_failure():
    # Verified real openFDA behavior: a true empty search is HTTP 404 with
    # this exact error body, not a 200 with an empty results array.
    respx.get(_510K_URL).mock(
        return_value=httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
    )
    async with httpx.AsyncClient() as client:
        result = await openfda_client.search_510k(
            client, product_name="Nonexistent Device Zzz", manufacturer="", aliases=[],
        )
    assert result.status == RetrievalStatus.MISS


@respx.mock
async def test_timeout_is_retrieval_failure_not_miss():
    respx.get(_510K_URL).mock(side_effect=httpx.TimeoutException("simulated timeout"))
    async with httpx.AsyncClient() as client:
        result = await openfda_client.search_510k(
            client, product_name="Some Device", manufacturer="", aliases=[],
        )
    assert result.status == RetrievalStatus.RETRIEVAL_FAILURE
    assert "timeout" in result.error.lower()


@respx.mock
async def test_server_error_is_retrieval_failure():
    respx.get(_510K_URL).mock(return_value=httpx.Response(503))
    async with httpx.AsyncClient() as client:
        result = await openfda_client.search_510k(client, product_name="X", manufacturer="", aliases=[])
    assert result.status == RetrievalStatus.RETRIEVAL_FAILURE


@respx.mock
async def test_ambiguous_de_novo_classification_lookup_is_miss_not_negative():
    # De Novo devices are resolved via classification.json only (no
    # /device/denovo.json exists) -- an ambiguous/empty lookup must surface
    # as MISS so the caller can mark the pillar UNKNOWN, never a negative.
    respx.get(_CLASSIFICATION_URL).mock(
        return_value=httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
    )
    async with httpx.AsyncClient() as client:
        result = await openfda_client.search_classification(
            client, product_name="Ambiguous De Novo Device", manufacturer="", aliases=[],
        )
    assert result.status == RetrievalStatus.MISS
    # Never a status implying a verified negative -- MISS is the only
    # signal this layer emits; classifying it as UNKNOWN-vs-negative is the
    # caller's job (Stage 3 / scoring enforcement), not this client's.
