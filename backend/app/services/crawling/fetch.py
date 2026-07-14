"""SSRF-guarded HTTP fetching for the crawler.

Every hop of a redirect chain is revalidated (build spec §10.3: "Revalidate
the destination after every redirect") by disabling httpx's automatic
redirect-following and looping manually, calling resolve_and_validate()
before each request.
"""

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from app.services.crawling.ssrf import resolve_and_validate

USER_AGENT = "MedTechComplianceAgent/0.1 (+local compliance research tool; respects robots.txt)"
MAX_REDIRECTS = 5
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    content_type: str | None
    content: bytes
    headers: dict[str, str]


async def safe_fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 15.0,
    max_bytes: int = 20 * 1024 * 1024,
) -> FetchResult:
    current_url = url
    for _ in range(MAX_REDIRECTS + 1):
        resolve_and_validate(current_url)  # raises SSRFBlockedError; propagates to caller

        response = await client.get(
            current_url,
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )

        if response.status_code in REDIRECT_STATUS_CODES and response.headers.get("location"):
            current_url = urljoin(current_url, response.headers["location"])
            await response.aclose()
            continue

        content = response.content
        if len(content) > max_bytes:
            await response.aclose()
            raise FetchError(f"Response from {current_url} exceeds max_bytes={max_bytes}")

        return FetchResult(
            final_url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            content=content,
            headers=dict(response.headers),
        )

    raise FetchError(f"Too many redirects starting from {url}")
