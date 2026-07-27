"""Brave Search API client -- the name-only submission's web-search fallback
(quick_scan/pipeline.py::run_quick_scan_identity_resolution). Only ever
called when openFDA/CMS retrieval on the typed name comes back with zero
hits, to propose a candidate site for the user to confirm before it's
fetched and analyzed -- never a general evidence-gathering search, and
never invoked when a document/link was already provided.
"""

from dataclasses import dataclass

import httpx

_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_TIMEOUT_SECONDS = 10.0


class BraveSearchError(Exception):
    pass


@dataclass
class WebSearchResult:
    title: str
    url: str
    snippet: str


async def search(query: str, api_key: str, count: int = 3) -> list[WebSearchResult]:
    """Returns [] on a MISS (search ran fine, nothing came back) same as any
    other retrieval source; raises BraveSearchError only for a genuine
    request failure (bad key, network error, rate limit) so the caller can
    tell the two apart rather than treating every empty result the same."""
    if not api_key:
        raise BraveSearchError("No Brave Search API key configured.")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                _SEARCH_URL,
                params={"q": query, "count": count},
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
                timeout=_TIMEOUT_SECONDS,
            )
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
        raise BraveSearchError(f"Brave Search request failed: {exc}") from exc

    if response.status_code != 200:
        raise BraveSearchError(f"Brave Search request failed ({response.status_code}): {response.text[:200]}")

    body = response.json()
    results = (body.get("web") or {}).get("results") or []
    return [
        WebSearchResult(
            title=r.get("title", "") or "", url=r.get("url", "") or "", snippet=r.get("description", "") or "",
        )
        for r in results
        if r.get("url")
    ][:count]
