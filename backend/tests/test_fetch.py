import httpx
import pytest
import respx

from app.services.crawling.fetch import FetchError, safe_fetch
from app.services.crawling.ssrf import SSRFBlockedError


@respx.mock
async def test_safe_fetch_returns_content_for_ordinary_page():
    respx.get("https://example.com/page").mock(
        return_value=httpx.Response(200, content=b"<html>hello</html>", headers={"content-type": "text/html"})
    )
    async with httpx.AsyncClient() as client:
        result = await safe_fetch(client, "https://example.com/page")
    assert result.status_code == 200
    assert result.content == b"<html>hello</html>"
    assert result.final_url == "https://example.com/page"


@respx.mock
async def test_safe_fetch_follows_redirect_chain():
    respx.get("https://example.com/old").mock(
        return_value=httpx.Response(301, headers={"location": "https://example.com/new"})
    )
    respx.get("https://example.com/new").mock(return_value=httpx.Response(200, content=b"final page"))
    async with httpx.AsyncClient() as client:
        result = await safe_fetch(client, "https://example.com/old")
    assert result.final_url == "https://example.com/new"
    assert result.content == b"final page"


@respx.mock
async def test_safe_fetch_blocks_redirect_into_private_ip():
    respx.get("https://example.com/redirect-to-internal").mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(SSRFBlockedError):
            await safe_fetch(client, "https://example.com/redirect-to-internal")


@respx.mock
async def test_safe_fetch_raises_on_redirect_loop():
    respx.get("https://example.com/a").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.com/b"})
    )
    respx.get("https://example.com/b").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.com/a"})
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="Too many redirects"):
            await safe_fetch(client, "https://example.com/a")


@respx.mock
async def test_safe_fetch_rejects_oversized_response():
    respx.get("https://example.com/huge").mock(
        return_value=httpx.Response(200, content=b"x" * 100)
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="max_bytes"):
            await safe_fetch(client, "https://example.com/huge", max_bytes=10)


async def test_safe_fetch_blocks_ssrf_before_any_network_call():
    async with httpx.AsyncClient() as client:
        with pytest.raises(SSRFBlockedError):
            await safe_fetch(client, "http://127.0.0.1:8000/internal")
