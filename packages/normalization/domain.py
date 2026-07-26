"""Domain normalization (spec 04 §3.2).

Reduce a URL/host to a canonical apex. This v1 uses a compact multi-label
public-suffix set covering the common ccTLD second levels; swap in the full
`publicsuffix2` list when the collector layer lands (ADR noted in spec 04).
The apex is the strongest company blocking/matching key.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# Common multi-label public suffixes (subset; full PSL wired in later).
_MULTI_LABEL_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "gov.uk",
        "ac.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "co.jp",
        "co.in",
        "com.br",
        "com.sg",
        "com.mx",
        "co.za",
    }
)

# Subdomains that are equivalent to the apex for company identity.
_APEX_EQUIVALENT_PREFIXES: frozenset[str] = frozenset({"www", "www2", "m", "en", "app"})

_HOST_RE = re.compile(r"^[a-z0-9.-]+$")


def normalize_host(value: str) -> str:
    """Extract a lowercase host from a URL or bare host string."""
    if not value:
        return ""
    value = value.strip().lower()
    if "://" not in value:
        value = "//" + value
    try:
        host = urlparse(value).hostname or ""
    except ValueError:
        # Malformed input (e.g. invalid IPv6 literal) — not a usable host.
        return ""
    return host.rstrip(".")


def apex_domain(value: str) -> str:
    """Reduce a URL/host to its registrable apex domain.

    ``https://www.acme.co.uk/team`` -> ``acme.co.uk``
    ``blog.acme.com`` -> ``acme.com``
    """
    host = normalize_host(value)
    if not host or not _HOST_RE.match(host):
        return ""
    # IP addresses and bare hostnames (e.g. localhost) are not registrable
    # domains — return the host unchanged rather than slicing labels.
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    last_three = ".".join(labels[-3:])
    if last_two in _MULTI_LABEL_SUFFIXES:
        # Registrable domain is the label before the multi-label suffix.
        return last_three if len(labels) >= 3 else host
    # Collapse apex-equivalent leading subdomains, then take the final two labels.
    if labels[0] in _APEX_EQUIVALENT_PREFIXES:
        labels = labels[1:]
    return ".".join(labels[-2:])
