import pytest

from app.services.crawling.ssrf import (
    SSRFBlockedError,
    resolve_and_validate,
    validate_url_scheme_and_host,
)


def test_allows_ordinary_https_url():
    assert validate_url_scheme_and_host("https://example.com/page") == "example.com"


def test_blocks_file_scheme():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("file:///etc/passwd")


def test_blocks_ftp_scheme():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("ftp://example.com/file")


def test_blocks_localhost_hostname():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("http://localhost/admin")


def test_blocks_literal_loopback_ip():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("http://127.0.0.1/admin")


def test_blocks_literal_loopback_ipv6():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("http://[::1]/admin")


def test_blocks_private_ipv4_ranges():
    for host in ["10.0.0.5", "172.16.0.5", "192.168.1.5"]:
        with pytest.raises(SSRFBlockedError):
            validate_url_scheme_and_host(f"http://{host}/")


def test_blocks_link_local_and_cloud_metadata():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("http://169.254.169.254/latest/meta-data/")


def test_blocks_url_with_no_hostname():
    with pytest.raises(SSRFBlockedError):
        validate_url_scheme_and_host("http:///path-only")


def test_resolve_and_validate_blocks_before_dns_for_literal_ip():
    # Should raise on the cheap literal-IP check, never reaching getaddrinfo.
    with pytest.raises(SSRFBlockedError, match="loopback"):
        resolve_and_validate("http://127.0.0.1:8000/")


def test_resolve_and_validate_rejects_unresolvable_host():
    with pytest.raises(SSRFBlockedError, match="DNS resolution failed"):
        resolve_and_validate("http://this-domain-should-not-exist-sonohl-test.invalid/")
