"""Network-location classification for local-first policy decisions."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def is_loopback_http_url(value: str) -> bool:
    """Return whether an absolute HTTP(S) URL resolves syntactically to loopback."""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return False

    host = parsed.hostname
    if host.lower() == "localhost":
        return True

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def private_grounding_allowed(
    endpoint: str,
    *,
    allow_remote_private_context: bool = False,
) -> bool:
    """Compatibility helper for the hard private-intelligence boundary.

    Remote private grounding is never allowed. The legacy opt-in argument is
    retained temporarily so old callers fail closed rather than regaining a
    remote-data path.
    """

    if allow_remote_private_context:
        return False
    return is_loopback_http_url(endpoint)
