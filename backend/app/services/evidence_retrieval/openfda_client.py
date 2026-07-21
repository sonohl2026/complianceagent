"""openFDA device-API client (quick_scan spec §1.1).

Verified against the real API (not just documentation) before writing this:
- A genuine no-match search returns HTTP 404 with body
  {"error": {"code": "NOT_FOUND", "message": "No matches found!"}} -- this is
  MISS (the source was searched and has nothing), never RETRIEVAL_FAILURE.
  Any other error (5xx, timeout, network, or a 404 NOT matching that exact
  shape) is RETRIEVAL_FAILURE.
- A hit returns {"meta": {...}, "results": [...]}.

There is deliberately NO /device/denovo.json function: that endpoint does not
exist. De Novo devices are resolved via search_classification() only, per
spec 1.1 point 2-3; an ambiguous/empty classification lookup for a
Stage-1-flagged De Novo device is surfaced as MISS by this client and must be
treated as UNKNOWN by the caller, never as a negative finding.
"""

import time

import httpx

from app.config import get_settings
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence

_TIMEOUT_SECONDS = 15.0

# One entry per real, documented openFDA device endpoint (spec 1.1). Do not
# add endpoints not in this list -- there is no /device/denovo.json.
_ENDPOINTS = {
    "510k": "device/510k.json",
    "pma": "device/pma.json",
    "classification": "device/classification.json",
    "recall": "device/recall.json",
    "enforcement": "device/enforcement.json",
    "event": "device/event.json",
    "udi": "device/udi.json",
}


def _search_field_for(endpoint: str) -> str:
    # Each endpoint indexes device identity under a different field name (and
    # sometimes nested under a sub-object) -- verified against real query
    # responses for every endpoint, not assumed uniform. Notably `udi` has no
    # top-level device_name (it's `brand_name`), and `event` (MAUDE) nests
    # device identity under a `device` array, searched via a dotted path
    # (confirmed working: device.brand_name:"...").
    if endpoint == "pma":
        return "trade_name"
    if endpoint in ("recall", "enforcement"):
        return "product_description"
    if endpoint == "udi":
        return "brand_name"
    if endpoint == "event":
        return "device.brand_name"
    return "device_name"  # 510k, classification


async def _query_endpoint(
    client: httpx.AsyncClient, base_url: str, endpoint: str, term: str, *, limit: int = 5
) -> SourceEvidence:
    field = _search_field_for(endpoint)
    url = f"{base_url}/{_ENDPOINTS[endpoint]}"
    params = {"search": f'{field}:"{term}"', "limit": limit}
    started = time.monotonic()
    try:
        response = await client.get(url, params=params, timeout=_TIMEOUT_SECONDS)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return SourceEvidence(
            source=f"openfda_{endpoint}", status=RetrievalStatus.RETRIEVAL_FAILURE,
            latency_ms=latency_ms, error=str(exc),
        )
    latency_ms = int((time.monotonic() - started) * 1000)

    if response.status_code == 404:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if body.get("error", {}).get("code") == "NOT_FOUND":
            return SourceEvidence(source=f"openfda_{endpoint}", status=RetrievalStatus.MISS, latency_ms=latency_ms)
        return SourceEvidence(
            source=f"openfda_{endpoint}", status=RetrievalStatus.RETRIEVAL_FAILURE,
            latency_ms=latency_ms, error=f"unexpected 404 body: {body}",
        )
    if response.status_code >= 500:
        return SourceEvidence(
            source=f"openfda_{endpoint}", status=RetrievalStatus.RETRIEVAL_FAILURE,
            latency_ms=latency_ms, error=f"HTTP {response.status_code}",
        )
    if response.status_code != 200:
        return SourceEvidence(
            source=f"openfda_{endpoint}", status=RetrievalStatus.RETRIEVAL_FAILURE,
            latency_ms=latency_ms, error=f"HTTP {response.status_code}: {response.text[:200]}",
        )

    body = response.json()
    results = body.get("results", [])
    if not results:
        return SourceEvidence(source=f"openfda_{endpoint}", status=RetrievalStatus.MISS, latency_ms=latency_ms)
    return SourceEvidence(
        source=f"openfda_{endpoint}", status=RetrievalStatus.HIT,
        latency_ms=latency_ms, data={"results": results},
    )


async def search_with_fallback(
    client: httpx.AsyncClient, endpoint: str, *, product_name: str, manufacturer: str, aliases: list[str],
) -> SourceEvidence:
    """Search order per spec 1.1: exact product name -> manufacturer -> aliases,
    stopping at the first HIT and recording which term matched. A MISS on
    every term is a genuine MISS (not a failure); any RETRIEVAL_FAILURE along
    the way short-circuits immediately (a transient/network problem, not
    evidence)."""
    base_url = get_settings().openfda_base_url
    candidates = [("exact", product_name)] + [("probable", manufacturer)] + [("uncertain", a) for a in aliases]
    last: SourceEvidence | None = None
    for confidence, term in candidates:
        if not term:
            continue
        result = await _query_endpoint(client, base_url, endpoint, term)
        if result.status == RetrievalStatus.RETRIEVAL_FAILURE:
            return result
        if result.status == RetrievalStatus.HIT:
            result.match_confidence = confidence
            return result
        last = result
    return last or SourceEvidence(source=f"openfda_{endpoint}", status=RetrievalStatus.MISS, latency_ms=0)


async def search_510k(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "510k", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_pma(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "pma", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_classification(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    """Also the De Novo resolution path (spec 1.1 point 1) -- classification
    entries for De Novo-created regulations appear here since there is no
    /device/denovo.json. A MISS here for a Stage-1-flagged De Novo device
    must be surfaced by the caller as UNKNOWN, never as evidence the device
    lacks a pathway."""
    return await search_with_fallback(client, "classification", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_recall(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "recall", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_enforcement(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "enforcement", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_event(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "event", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_udi(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "udi", product_name=product_name, manufacturer=manufacturer, aliases=aliases)
