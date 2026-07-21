"""Shared text helpers for social/community collectors.

Community posts (HN, Reddit) name the buyer's company inline — sometimes as a full
URL, often as a bare domain with the scheme dropped ("we're acme.co"). These helpers
pull the first real external domain out of such text and strip HTML, so each collector
doesn't reimplement it.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable

from normalization import apex_domain

_URL_RE = re.compile(r'https?://[^\s"<>)]+', re.IGNORECASE)
_BARE_RE = re.compile(r"\b((?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,})\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
# Restrict bare-domain matches to real TLDs so tech tokens like "node.js" / "next.js"
# (TLD "js") are never mistaken for a company domain.
_ALLOWED_TLDS = {"com", "io", "co", "ai", "net", "org", "dev", "app", "xyz", "tech",
                 "design", "studio", "agency", "us", "uk", "ca", "de", "so", "sh", "me"}


def strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", html.unescape(text or "")).strip()


def company_slug(name: str) -> str:
    """A stable key for a company we know by NAME but not domain (aggregator posts).
    Lets such leads still be captured + de-duped by name. Empty if unusable."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug[:60]


def first_external_domain(raw: str, exclude: Iterable[str] = ()) -> str | None:
    """First real external apex domain in `raw` (full URL preferred, else bare),
    skipping any host in `exclude` (e.g. the platform's own domains)."""
    unescaped = html.unescape(raw or "")
    excl = set(exclude)
    for m in _URL_RE.finditer(unescaped):
        apex = apex_domain(m.group(0).rstrip(".,);"))
        if apex and apex not in excl:
            return apex
    for m in _BARE_RE.finditer(unescaped):
        cand = m.group(1).lower().rstrip(".")
        if cand.rsplit(".", 1)[-1] in _ALLOWED_TLDS:
            apex = apex_domain(cand)
            if apex and apex not in excl:
                return apex
    return None
