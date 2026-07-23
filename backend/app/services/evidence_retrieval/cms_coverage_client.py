"""CMS Coverage API client (quick_scan spec §1.2).

Verified against the real, live API before writing this (not just the
Swagger stub at /docs/swagger, which is empty -- the real endpoint reference
is CMS's own changelog at /docs/release_notes):

- No API key anywhere (removed Feb 8, 2024) -- every call below is anonymous.
- UNLICENSED (confirmed via real 200 responses, no auth header):
    GET /v1/reports/national-coverage-ncd        (full NCD listing)
    GET /v1/reports/local-coverage-final-lcds     (full LCD listing)
    GET /v1/reports/local-coverage-articles       (full Article listing)
    GET /v1/data/ncd?ncdid=X&ncdver=Y             (NCD detail)
  None of these accept a working server-side keyword filter (a `?title=`
  param was silently ignored in testing) -- matching is done client-side
  against each listing's `title` field.
- LICENSED (confirmed via real 401 without a token; CMS's own changelog:
  "Required for Local Coverage Article and LCD endpoints"):
    GET /v1/data/lcd?lcdid=X&lcdver=Y
    GET /v1/data/article?articleid=X&articlever=Y
  Token: GET /v1/metadata/license-agreement/ -- a bare unauthenticated GET
  immediately returns a usable bearer token (no separate POST/accept step).
  Its own response text states that visiting this URL constitutes accepting
  the AMA CPT / ADA CDT / AHA UB-04 license agreements. Token is valid one
  hour per that same response. Because merely calling this URL is the
  acceptance act, this client must NEVER call it unless
  settings["cms_license_accepted"] is True -- that settings toggle is the
  user's own, deliberate acceptance, not something this code decides for
  them.

The three listing endpoints return large payloads (LCD ~450KB/970 rows,
Article ~1MB/2169 rows, several seconds to fetch) and change infrequently, so
this module keeps a short-TTL in-memory cache -- without it, quick_scan's
<30s p50 target would be at risk from re-fetching megabytes on every run.
"""

import time
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.services.evidence_retrieval.types import RetrievalStatus, SourceEvidence

_TIMEOUT_SECONDS = 15.0
_LISTING_CACHE_TTL_SECONDS = 3600  # matches the API's own ~hourly data-capture cadence
_TOKEN_TTL_SECONDS = 3600  # per the license-agreement endpoint's own response text

_REPORT_PATHS = {
    "ncd": "v1/reports/national-coverage-ncd",
    "lcd": "v1/reports/local-coverage-final-lcds",
    "article": "v1/reports/local-coverage-articles",
}

_DETAIL_PATHS = {
    "ncd": "v1/data/ncd",
    "lcd": "v1/data/lcd",
    "article": "v1/data/article",
}
_DETAIL_ID_PARAMS = {
    "ncd": ("ncdid", "ncdver"),
    "lcd": ("lcdid", "lcdver"),
    "article": ("articleid", "articlever"),
}
_LICENSED_RESOURCES = {"lcd", "article"}  # ncd detail is unlicensed; confirmed live


@dataclass
class _CachedListing:
    fetched_at: float
    rows: list[dict]


_listing_cache: dict[str, _CachedListing] = {}
_token_cache: dict[str, tuple[str, float]] = {}  # {"token": (value, expires_at_monotonic)}


async def _fetch_listing(client: httpx.AsyncClient, resource: str) -> SourceEvidence:
    cached = _listing_cache.get(resource)
    now = time.monotonic()
    if cached is not None and (now - cached.fetched_at) < _LISTING_CACHE_TTL_SECONDS:
        return SourceEvidence(
            source=f"cms_{resource}_listing", status=RetrievalStatus.HIT,
            latency_ms=0, data={"rows": cached.rows, "cached": True},
        )

    base_url = get_settings().cms_coverage_base_url
    url = f"{base_url}/{_REPORT_PATHS[resource]}"
    started = time.monotonic()
    try:
        response = await client.get(url, timeout=_TIMEOUT_SECONDS)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return SourceEvidence(
            source=f"cms_{resource}_listing", status=RetrievalStatus.RETRIEVAL_FAILURE,
            latency_ms=latency_ms, error=str(exc),
        )
    latency_ms = int((time.monotonic() - started) * 1000)
    if response.status_code != 200:
        return SourceEvidence(
            source=f"cms_{resource}_listing", status=RetrievalStatus.RETRIEVAL_FAILURE,
            latency_ms=latency_ms, error=f"HTTP {response.status_code}",
        )

    body = response.json()
    rows = body.get("data", [])
    _listing_cache[resource] = _CachedListing(fetched_at=now, rows=rows)
    if not rows:
        return SourceEvidence(source=f"cms_{resource}_listing", status=RetrievalStatus.MISS, latency_ms=latency_ms)
    return SourceEvidence(
        source=f"cms_{resource}_listing", status=RetrievalStatus.HIT,
        latency_ms=latency_ms, data={"rows": rows, "cached": False},
    )


# Qualifier pairs the title match doesn't weight against the head noun it
# modifies -- e.g. "continuous glucose monitor" is a substring of both
# "Continuous Glucose Monitors" AND "Implantable Continuous Glucose
# Monitors", so a device known (from Stage 1's own intended_use/
# technology_type text) to be non-implantable/wearable can still match an
# implantable-only policy. Real incident: fixture 4 (Dexcom G7, external/
# wearable) matched an LCD titled "Implantable Continuous Glucose Monitors"
# this way -- see status report and run_benchmark.py's module docstring.
# Each pair is checked in both directions.
_QUALIFIER_PAIRS = [
    ("implantable", "non-implantable"),
    ("implantable", "wearable"),
    ("implantable", "external"),
    ("pediatric", "adult"),
    ("unilateral", "bilateral"),
    ("internal", "external"),
    ("left", "right"),
    ("initial", "subsequent"),
]


def _qualifier_contradicts(title: str, device_context: str) -> bool:
    """True if the title asserts one qualifier and the device's own
    description asserts its pair's opposite -- e.g. title says "implantable",
    device text says "wearable"/"external". Deliberately skips a pair if the
    device text mentions BOTH sides (ambiguous, not a clean contradiction)
    rather than guessing which one actually applies."""
    if not device_context:
        return False
    title_l, device_l = title.lower(), device_context.lower()
    for a, b in _QUALIFIER_PAIRS:
        a_in_device, b_in_device = a in device_l, b in device_l
        if a_in_device and b_in_device:
            continue
        if a in title_l and b_in_device:
            return True
        if b in title_l and a_in_device:
            return True
    return False


async def search_unlicensed(
    client: httpx.AsyncClient, resource: str, candidate_terms: list[str], device_context: str = "",
) -> SourceEvidence:
    """Client-side keyword match against a resource's full title listing
    (spec: "search with procedure/condition keywords... MCD indexes services,
    not products" -- candidate_terms should be Stage-1's condition/procedure
    terms, not the brand name). Always callable, no license required.

    device_context (Stage 1's intended_use + technology_type + product_name,
    free text -- see orchestrator.py's call site) is used ONLY to reject a
    title match whose qualifier contradicts the device's own description; it
    is never itself used as a search term, so this can't introduce new false
    HITs, only remove specific false ones."""
    listing_evidence = await _fetch_listing(client, resource)
    if listing_evidence.status != RetrievalStatus.HIT:
        return SourceEvidence(source=f"cms_{resource}", status=listing_evidence.status,
                               latency_ms=listing_evidence.latency_ms, error=listing_evidence.error)

    rows = listing_evidence.data["rows"]
    terms_lower = [t.lower() for t in candidate_terms if t]
    matches = [row for row in rows if any(t in row.get("title", "").lower() for t in terms_lower)]
    if not matches:
        return SourceEvidence(source=f"cms_{resource}", status=RetrievalStatus.MISS, latency_ms=listing_evidence.latency_ms)

    kept = [m for m in matches if not _qualifier_contradicts(m.get("title", ""), device_context)]
    excluded = [m for m in matches if m not in kept]
    if not kept:
        return SourceEvidence(
            source=f"cms_{resource}", status=RetrievalStatus.MISS, latency_ms=listing_evidence.latency_ms,
            data={
                "reason": "qualifier_contradiction",
                "note": (
                    f"{len(excluded)} title match(es) excluded: title qualifier contradicts the device's own "
                    "description (e.g. implantable vs non-implantable) -- not cited as evidence."
                ),
                "excluded_titles": [m.get("title") for m in excluded],
            },
        )
    return SourceEvidence(
        source=f"cms_{resource}", status=RetrievalStatus.HIT,
        latency_ms=listing_evidence.latency_ms, data={"matches": kept[:10]},
    )


async def acquire_license_token(client: httpx.AsyncClient, settings: dict) -> str | None:
    """Never called unless settings["cms_license_accepted"] is True -- flipping
    that toggle in Settings IS the user's acceptance of the AMA/ADA/AHA
    license text this endpoint returns; this code does not decide that for
    them. Returns None (never raises) if the flag is off, so callers can
    treat "no token" as just another reason to fall back to unlicensed
    evidence."""
    if not settings.get("cms_license_accepted"):
        return None

    cached = _token_cache.get("token")
    if cached is not None:
        value, expires_at = cached
        if time.monotonic() < expires_at:
            return value

    base_url = get_settings().cms_coverage_base_url
    url = f"{base_url}/v1/metadata/license-agreement/"
    response = await client.get(url, timeout=_TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    token = body["data"][0]["Token"]
    _token_cache["token"] = (token, time.monotonic() + _TOKEN_TTL_SECONDS)
    return token


async def get_licensed_document(
    client: httpx.AsyncClient, resource: str, doc_id: str, version: str, settings: dict,
) -> SourceEvidence:
    """Full document detail for lcd/article (gated) or ncd (not actually
    gated, but exposed here too for a uniform call shape). Returns MISS with
    an explanatory reason -- never RETRIEVAL_FAILURE -- when the license
    toggle is off, since this isn't a retrieval problem, it's a deliberate
    product-configuration state."""
    if resource in _LICENSED_RESOURCES and not settings.get("cms_license_accepted"):
        return SourceEvidence(
            source=f"cms_{resource}_detail", status=RetrievalStatus.MISS,
            latency_ms=0, data={"reason": "cms_license_not_accepted"},
        )

    token = await acquire_license_token(client, settings) if resource in _LICENSED_RESOURCES else None
    id_param, ver_param = _DETAIL_ID_PARAMS[resource]
    base_url = get_settings().cms_coverage_base_url
    url = f"{base_url}/{_DETAIL_PATHS[resource]}"
    params = {id_param: doc_id, ver_param: version}
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    started = time.monotonic()
    try:
        response = await client.get(url, params=params, headers=headers, timeout=_TIMEOUT_SECONDS)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        return SourceEvidence(source=f"cms_{resource}_detail", status=RetrievalStatus.RETRIEVAL_FAILURE,
                               latency_ms=latency_ms, error=str(exc))

    if response.status_code == 401 and token is not None:
        # Refresh-on-401: cached token may have been invalidated server-side; retry once.
        _token_cache.pop("token", None)
        token = await acquire_license_token(client, settings)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = await client.get(url, params=params, headers=headers, timeout=_TIMEOUT_SECONDS)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return SourceEvidence(source=f"cms_{resource}_detail", status=RetrievalStatus.RETRIEVAL_FAILURE,
                                   latency_ms=latency_ms, error=str(exc))

    latency_ms = int((time.monotonic() - started) * 1000)
    if response.status_code != 200:
        return SourceEvidence(source=f"cms_{resource}_detail", status=RetrievalStatus.RETRIEVAL_FAILURE,
                               latency_ms=latency_ms, error=f"HTTP {response.status_code}")

    body = response.json()
    data = body.get("data", [])
    if not data:
        return SourceEvidence(source=f"cms_{resource}_detail", status=RetrievalStatus.MISS, latency_ms=latency_ms)
    return SourceEvidence(source=f"cms_{resource}_detail", status=RetrievalStatus.HIT,
                           latency_ms=latency_ms, data={"document": data[0]})
