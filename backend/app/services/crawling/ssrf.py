"""SSRF protection for the website crawler.

Build spec §10.3: block file://, ftp://, localhost, private/link-local IPv4
and IPv6 ranges, cloud metadata endpoints, and redirects into blocked
ranges; revalidate the destination after every redirect.

Honest limitation (documented, not silently assumed away): this validates
the resolved IP immediately before connecting, which closes the common
SSRF vectors (literal private/loopback URLs, metadata-endpoint URLs,
malicious open-redirect chains, since every redirect hop is revalidated
here too) but does not eliminate a theoretical DNS-rebinding attack where
a hostname's DNS record changes between our validation and the underlying
TCP connect a few milliseconds later. Fully closing that gap requires
pinning the validated IP into the socket layer (a custom transport), which
is tracked as a follow-up hardening item rather than silently claimed done.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}

# Cloud metadata endpoints are technically "link-local" (169.254.0.0/16) and
# would already be blocked by the link-local check, but are called out
# explicitly since they're the single most common real-world SSRF target.
METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),  # AWS/Azure/GCP/OCI metadata
    ipaddress.ip_address("fd00:ec2::254"),  # AWS IMDSv2 IPv6
}

BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}


class SSRFBlockedError(Exception):
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Blocked {url!r}: {reason}")


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if ip in METADATA_ADDRESSES:
        return "cloud metadata address"
    if ip.is_loopback:
        return "loopback address"
    if ip.is_private:
        return "private address"
    if ip.is_link_local:
        return "link-local address"
    if ip.is_multicast:
        return "multicast address"
    if ip.is_reserved:
        return "reserved address"
    if ip.is_unspecified:
        return "unspecified address"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked_ip(ip.ipv4_mapped)
    return None


def validate_url_scheme_and_host(url: str) -> str:
    """Cheap, pre-DNS checks: scheme allowlist and literal blocked hostnames
    or IP literals. Returns the hostname on success."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SSRFBlockedError(url, f"scheme {parts.scheme!r} is not allowed")
    if not parts.hostname:
        raise SSRFBlockedError(url, "URL has no hostname")

    hostname = parts.hostname.lower()
    if hostname in BLOCKED_HOSTNAMES:
        raise SSRFBlockedError(url, f"hostname {hostname!r} is blocked")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        reason = _is_blocked_ip(literal_ip)
        if reason:
            raise SSRFBlockedError(url, reason)

    return hostname


def resolve_and_validate(url: str) -> list[str]:
    """Full check: scheme/hostname allowlist, then DNS resolution, then
    validate every resolved address is public. Raises SSRFBlockedError if
    any check fails. Returns the resolved IP address strings on success
    (informational / for logging, not used to pin the connection)."""
    hostname = validate_url_scheme_and_host(url)

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(url, f"DNS resolution failed: {exc}") from exc

    resolved_ips = []
    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        reason = _is_blocked_ip(ip)
        if reason:
            raise SSRFBlockedError(url, f"resolves to {ip_str} ({reason})")
        resolved_ips.append(ip_str)

    if not resolved_ips:
        raise SSRFBlockedError(url, "DNS resolution returned no addresses")

    return resolved_ips
