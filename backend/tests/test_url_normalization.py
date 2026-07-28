from app.api.v1.quick_scans import _normalize_url


def test_bare_domain_gets_https_prefix():
    assert _normalize_url("sonohl.com") == "https://sonohl.com"


def test_already_has_https_is_untouched():
    assert _normalize_url("https://sonohl.com") == "https://sonohl.com"


def test_already_has_http_is_untouched():
    assert _normalize_url("http://sonohl.com") == "http://sonohl.com"


def test_case_insensitive_scheme_is_untouched():
    assert _normalize_url("HTTPS://sonohl.com") == "HTTPS://sonohl.com"


def test_strips_whitespace_before_checking():
    assert _normalize_url("  sonohl.com  ") == "https://sonohl.com"
