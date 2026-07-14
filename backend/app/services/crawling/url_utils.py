"""URL normalization and same-registrable-domain checks.

Deliberately dependency-free (no tldextract / public-suffix-list download)
so the crawler works fully offline after the initial `pip install`. The
two-label heuristic below is wrong for some multi-part public suffixes
(app.co.uk, example.com.au) -- the small SPECIAL_SUFFIXES table covers the
common real-world cases; anything else falls back to a plain
last-two-labels comparison, which is right far more often than not for a
same-company-website crawl scope.
"""

from urllib.parse import urldefrag, urlsplit, urlunsplit

# Public suffixes longer than one label, common enough to special-case.
SPECIAL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk",
    "com.au", "net.au", "org.au",
    "co.jp", "co.nz", "co.in",
    "com.br", "com.mx",
}


def normalize_url(url: str) -> str:
    """Strip fragments, lowercase scheme/host, drop default ports, drop a
    trailing slash on bare paths, so equivalent URLs compare equal."""
    url, _fragment = urldefrag(url)
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    default_port = {"http": 80, "https": 443}.get(scheme)
    netloc = hostname if port is None or port == default_port else f"{hostname}:{port}"
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
        if not path:
            path = "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def registrable_domain(hostname: str) -> str:
    hostname = hostname.lower().rstrip(".")
    labels = hostname.split(".")
    if len(labels) <= 2:
        return hostname
    last_two = ".".join(labels[-2:])
    if last_two in SPECIAL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def same_registrable_domain(host_a: str, host_b: str) -> bool:
    return registrable_domain(host_a) == registrable_domain(host_b)


def is_in_crawl_scope(url: str, root_hostname: str, *, follow_subdomains: bool) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    if not hostname:
        return False
    if follow_subdomains:
        return same_registrable_domain(hostname, root_hostname)
    return hostname == root_hostname.lower()


def matches_any_pattern(url: str, patterns: list[str]) -> bool:
    return any(pattern in url for pattern in patterns)
