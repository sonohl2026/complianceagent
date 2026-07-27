import httpx
import pytest
import respx

from app.services.web_search.brave_client import BraveSearchError, search

_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


@respx.mock
async def test_search_returns_results():
    respx.get(_SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {"title": "Acme Widget", "url": "https://acme.example/widget", "description": "The widget."},
                        {"title": "Other", "url": "https://other.example", "description": "Not it."},
                    ]
                }
            },
        )
    )
    results = await search("Acme Widget", api_key="key", count=2)
    assert len(results) == 2
    assert results[0].title == "Acme Widget"
    assert results[0].url == "https://acme.example/widget"
    assert results[0].snippet == "The widget."


@respx.mock
async def test_search_no_results_is_empty_list():
    respx.get(_SEARCH_URL).mock(return_value=httpx.Response(200, json={"web": {"results": []}}))
    results = await search("Nonexistent Gadget 9000", api_key="key")
    assert results == []


@respx.mock
async def test_search_drops_results_missing_a_url():
    respx.get(_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"web": {"results": [{"title": "No URL", "description": "x"}]}})
    )
    results = await search("query", api_key="key")
    assert results == []


@respx.mock
async def test_search_raises_on_non_200():
    respx.get(_SEARCH_URL).mock(return_value=httpx.Response(401, text="bad key"))
    with pytest.raises(BraveSearchError):
        await search("query", api_key="bad-key")


async def test_search_raises_without_an_api_key():
    with pytest.raises(BraveSearchError):
        await search("query", api_key="")
