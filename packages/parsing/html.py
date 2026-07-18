"""HTML parser (spec 03 §3).

Extracts title, visible text, links, meta/OpenGraph, and JSON-LD using the
stdlib ``html.parser`` backend (no lxml dependency). Deterministic — the same
bytes always yield the same ParsedDocument (golden-fixture friendly, spec 09).
"""

from __future__ import annotations

import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import ParsedDocument, ParsedLink

_SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}


def parse_html(body: bytes, url: str) -> ParsedDocument:
    soup = BeautifulSoup(body, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    meta: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if key and content:
            meta[key.lower()] = content.strip()

    for tag in soup(list(_SKIP_TAGS)):
        tag.decompose()

    text = " ".join(soup.get_text(separator=" ").split())

    links: list[ParsedLink] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "javascript:", "tel:")):
            continue
        links.append(
            ParsedLink(
                href=urljoin(url, href),
                text=" ".join(a.get_text(separator=" ").split())[:200],
                rel=" ".join(a.get("rel", [])) or None,
            )
        )

    structured = _extract_json_ld(soup)

    return ParsedDocument(
        url=url, title=title, text=text, links=links, meta=meta, structured=structured
    )


def _extract_json_ld(soup: BeautifulSoup) -> dict:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    return {}
