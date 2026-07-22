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
treated as UNKNOWN by the caller, never as a negative finding. (The spec's
point 2 HTML-scrape fallback against accessdata.fda.gov's CDRH De Novo
database page is explicitly deep-dive-tier only -- out of scope for
quick_scan, not attempted here.)

RESULT VERIFICATION (added after live testing surfaced real false positives --
see conversation record): openFDA's search is a free-text/phrase match, not
exact equality, so a search term that misses on the product's own name can
fall back to matching an entirely unrelated device. Two concrete failures
this fixes:
- LumineticsCore/IDx-DR: name search for "LumineticsCore" (its current
  marketing name -- FDA's own records still only know it as "IDx-DR", the
  2018 De Novo grant name) misses; manufacturer-name fallback ("Digital
  Diagnostics") then matched Hologic's unrelated "Genius Digital Diagnostics
  System" purely because that STRING appears inside Hologic's own device
  name. A wrong-device "hit" is worse than an honest MISS -- every result is
  now checked against the target product's own name/aliases before being
  accepted; a mismatch demotes it to MISS and the fallback chain continues
  (aliases are tried before manufacturer specifically so a device's own
  known alternate name is preferred over the much weaker manufacturer
  signal).
- Free-text fields (recall/enforcement's product_description, MAUDE's
  device sub-object) can genuinely contain the target name while being
  about a *different* product entirely -- e.g. Tandem's t:slim X2 pump
  recall literally says "...when using Dexcom G7 sensor", which would
  substring-match "Dexcom G7" without being a Dexcom recall at all. For
  these three endpoints, a name-field match is not accepted unless the
  record's own firm/manufacturer field also plausibly corresponds.
"""

import re
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

# These endpoints' identity field is a free-text description/sub-object that
# can genuinely mention an unrelated product's name (see module docstring) --
# for these, a name match alone isn't accepted; the record's own firm field
# must also plausibly correspond to the target manufacturer.
_REQUIRE_FIRM_MATCH = {"recall", "enforcement", "event"}

# classification.json describes a generic regulation/device-TYPE name (e.g.
# "Diabetic Retinopathy Detection Device"), never a specific product's brand
# -- even a verified match here is a category-level hint, not confirmed
# product identity, so it's never labeled "exact".
_CATEGORY_LEVEL_ENDPOINTS = {"classification"}


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


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _plausible_match(candidate: str | None, targets: list[str]) -> bool:
    """True if candidate text plausibly refers to one of the targets --
    normalized substring containment (either direction) or full token-subset
    overlap. Deliberately loose enough to match "SAPIEN 3" against "Edwards
    SAPIEN 3 Ultra Transcatheter Heart Valve System", but tight enough to
    reject "Diabetic Retinopathy Detection Device" against "IDx-DR" (no
    shared tokens) or "Tandem Diabetes Care, Inc." against "Dexcom" (no
    shared tokens)."""
    if not candidate:
        return False
    norm_candidate = _normalize(candidate)
    if not norm_candidate:
        return False
    candidate_tokens = set(norm_candidate.split())
    for target in targets:
        if not target:
            continue
        norm_target = _normalize(target)
        if not norm_target:
            continue
        if norm_target in norm_candidate or norm_candidate in norm_target:
            return True
        target_tokens = set(norm_target.split())
        if target_tokens and target_tokens.issubset(candidate_tokens):
            return True
    return False


def _identity_text(endpoint: str, result: dict) -> str | None:
    """The same field _search_field_for names, read back out of an actual
    result record (handles event's nested device array, which the dotted
    search-query path doesn't require unpacking but reading the JSON does)."""
    if endpoint == "pma":
        return result.get("trade_name")
    if endpoint in ("recall", "enforcement"):
        return result.get("product_description")
    if endpoint == "udi":
        return result.get("brand_name")
    if endpoint == "event":
        devices = result.get("device") or []
        return devices[0].get("brand_name") if devices else None
    return result.get("device_name")  # 510k, classification


def _firm_text(endpoint: str, result: dict) -> str | None:
    if endpoint in ("510k", "pma"):
        return result.get("applicant")
    if endpoint in ("recall", "enforcement"):
        return result.get("recalling_firm")
    if endpoint == "udi":
        return result.get("company_name")
    if endpoint == "event":
        devices = result.get("device") or []
        return devices[0].get("manufacturer_d_name") if devices else None
    return None  # classification has no per-product firm field


def _verify_result(endpoint: str, result: dict, *, product_name: str, manufacturer: str, aliases: list[str]) -> bool:
    """A returned record is only accepted if its own identity plausibly
    corresponds to the target product. Never trust a search hit at face
    value just because a term matched somewhere -- a wrong-device match is
    worse than an honest MISS."""
    targets = [product_name, *aliases]
    if not _plausible_match(_identity_text(endpoint, result), targets):
        return False
    if endpoint in _REQUIRE_FIRM_MATCH and manufacturer:
        if not _plausible_match(_firm_text(endpoint, result), [manufacturer]):
            return False
    return True


def _confidence_for(endpoint: str, term_kind: str) -> str:
    # Once verified, a hit from the product's own name or a known alias is
    # as trustworthy as any structured record gets. A hit that only ever
    # matched via the manufacturer name is inherently a weaker, indirect
    # signal even after passing verification (the search itself wasn't
    # against the product's own identity). classification.json never earns
    # "exact" -- see _CATEGORY_LEVEL_ENDPOINTS.
    if endpoint in _CATEGORY_LEVEL_ENDPOINTS:
        return "probable"
    return "exact" if term_kind in ("name", "alias") else "probable"


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
    """Search order: exact product name -> known aliases -> manufacturer name,
    stopping at the first HIT whose results verify against the target
    product's own identity (see _verify_result). Manufacturer is tried last
    and is the weakest signal -- it's a real device's OWNER, not its name, so
    searching it against a device-identity field is inherently prone to
    matching a different product by the same company (or one that merely
    mentions the company). A HIT whose results all fail verification is
    treated as a MISS and the fallback continues to the next term -- a
    wrong-device match must never be surfaced as evidence. Any
    RETRIEVAL_FAILURE along the way short-circuits immediately (a
    transient/network problem, not evidence)."""
    base_url = get_settings().openfda_base_url
    candidates = [("name", product_name)] + [("alias", a) for a in aliases] + [("manufacturer", manufacturer)]
    last: SourceEvidence | None = None
    for term_kind, term in candidates:
        if not term:
            continue
        result = await _query_endpoint(client, base_url, endpoint, term)
        if result.status == RetrievalStatus.RETRIEVAL_FAILURE:
            return result
        if result.status == RetrievalStatus.HIT:
            verified = [
                r for r in result.data["results"]
                if _verify_result(endpoint, r, product_name=product_name, manufacturer=manufacturer, aliases=aliases)
            ]
            if verified:
                result.data = {"results": verified}
                result.match_confidence = _confidence_for(endpoint, term_kind)
                return result
            last = SourceEvidence(source=f"openfda_{endpoint}", status=RetrievalStatus.MISS, latency_ms=result.latency_ms)
            continue
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
    lacks a pathway. In practice classification.json's device_name is a
    generic regulation/category name (e.g. "Diabetic Retinopathy Detection
    Device"), not a brand -- a genuine brand-name match here is rare, and a
    MISS is the common, correct, spec-anticipated outcome for most specific
    products (see search_with_fallback's confidence rules: a classification
    hit is never labeled "exact")."""
    return await search_with_fallback(client, "classification", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_recall(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "recall", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_enforcement(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "enforcement", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_event(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "event", product_name=product_name, manufacturer=manufacturer, aliases=aliases)


async def search_udi(client, *, product_name, manufacturer, aliases) -> SourceEvidence:
    return await search_with_fallback(client, "udi", product_name=product_name, manufacturer=manufacturer, aliases=aliases)
