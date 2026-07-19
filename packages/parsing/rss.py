"""RSS / Atom feed parser (spec 03 §7 rss_blog).

Stdlib XML only (no extra dependency), tolerant of both RSS 2.0 and Atom.
Deterministic — golden-fixture friendly.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class RssItem:
    title: str
    link: str
    author: str | None
    summary: str
    published: str | None


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_rss(body: bytes) -> list[RssItem]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []

    items: list[RssItem] = []

    # RSS 2.0: <rss><channel><item>...
    for item in root.iter("item"):
        author = _text(item.find("author")) or _text(item.find("{http://purl.org/dc/elements/1.1/}creator"))
        items.append(RssItem(
            title=_text(item.find("title")),
            link=_text(item.find("link")),
            author=author or None,
            summary=_text(item.find("description")),
            published=_text(item.find("pubDate")) or None,
        ))

    # Atom: <feed><entry>...
    for entry in root.iter(f"{_ATOM}entry"):
        link_el = entry.find(f"{_ATOM}link")
        link = link_el.get("href") if link_el is not None else ""
        author_el = entry.find(f"{_ATOM}author")
        author = _text(author_el.find(f"{_ATOM}name")) if author_el is not None else ""
        items.append(RssItem(
            title=_text(entry.find(f"{_ATOM}title")),
            link=link,
            author=author or None,
            summary=_text(entry.find(f"{_ATOM}summary")) or _text(entry.find(f"{_ATOM}content")),
            published=_text(entry.find(f"{_ATOM}updated")) or None,
        ))

    return items
