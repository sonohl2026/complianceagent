from app.services.crawling.url_utils import (
    is_in_crawl_scope,
    normalize_url,
    registrable_domain,
    same_registrable_domain,
)


def test_normalize_strips_fragment():
    assert normalize_url("https://example.com/page#section") == "https://example.com/page"


def test_normalize_lowercases_scheme_and_host():
    assert normalize_url("HTTPS://Example.COM/Page") == "https://example.com/Page"


def test_normalize_drops_default_port():
    assert normalize_url("https://example.com:443/page") == "https://example.com/page"
    assert normalize_url("http://example.com:80/page") == "http://example.com/page"


def test_normalize_keeps_non_default_port():
    assert normalize_url("https://example.com:8443/page") == "https://example.com:8443/page"


def test_normalize_strips_trailing_slash_except_root():
    assert normalize_url("https://example.com/page/") == "https://example.com/page"
    assert normalize_url("https://example.com/") == "https://example.com/"
    assert normalize_url("https://example.com") == "https://example.com/"


def test_registrable_domain_simple():
    assert registrable_domain("www.sonohl.com") == "sonohl.com"
    assert registrable_domain("sonohl.com") == "sonohl.com"


def test_registrable_domain_handles_special_multi_part_suffix():
    assert registrable_domain("shop.example.co.uk") == "example.co.uk"


def test_same_registrable_domain_ignores_subdomain():
    assert same_registrable_domain("www.sonohl.com", "docs.sonohl.com") is True


def test_same_registrable_domain_rejects_different_company():
    assert same_registrable_domain("sonohl.com", "competitor.com") is False


def test_scope_check_without_subdomains_requires_exact_host():
    assert is_in_crawl_scope("https://sonohl.com/page", "sonohl.com", follow_subdomains=False) is True
    assert (
        is_in_crawl_scope("https://blog.sonohl.com/page", "sonohl.com", follow_subdomains=False)
        is False
    )


def test_scope_check_with_subdomains_allows_subdomain():
    assert (
        is_in_crawl_scope("https://blog.sonohl.com/page", "sonohl.com", follow_subdomains=True)
        is True
    )


def test_scope_check_rejects_offsite_link():
    assert is_in_crawl_scope("https://evil.com/page", "sonohl.com", follow_subdomains=True) is False
