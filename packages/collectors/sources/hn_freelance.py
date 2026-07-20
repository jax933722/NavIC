"""hn_freelance collector (spec 03 §7) — automated inbound from HN "Seeking Freelancer".

Monitors Hacker News' monthly *"Ask HN: Freelancer? Seeking freelancer?"* threads via
the free, no-auth Algolia HN Search API (`https://hn.algolia.com/api/v1/...`). Those
threads are a public firehose of buyers posting exactly the requests we want — e.g.
"SEEKING FREELANCER | Acme (acme.com) | Remote | need a React/Node dev, $8k/mo".

Only the buyer side is ingested: comments that begin with "SEEKING FREELANCER" (the
"SEEKING WORK" comments are freelancers offering, not buying, and are skipped). Each
buyer comment becomes the company it links to + a solicitation signal (service,
budget, timeline, stack — all lifted by the classifier). Fully within HN's terms;
no credentials, no cost. Runs on the scheduler like any other collector.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register

_URL_RE = re.compile(r'https?://[^\s"<>)]+', re.IGNORECASE)
# Bare domains ("acme.com", "brightbrew.co") — HN posters often omit the scheme.
_BARE_RE = re.compile(r"\b((?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,})\b", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_HN_HOSTS = {"news.ycombinator.com", "ycombinator.com", "hn.algolia.com", "algolia.com"}
# Restrict bare-domain matches to real TLDs so tech tokens like "node.js" / "next.js"
# (TLD "js") are never mistaken for a company domain.
_ALLOWED_TLDS = {"com", "io", "co", "ai", "net", "org", "dev", "app", "xyz", "tech",
                 "design", "studio", "agency", "us", "uk", "ca", "de", "so", "sh", "me"}


def _clean(text: str) -> str:
    return _TAG_RE.sub(" ", html.unescape(text or "")).strip()


def _first_external_domain(raw_html: str) -> str | None:
    unescaped = html.unescape(raw_html or "")
    for m in _URL_RE.finditer(unescaped):
        apex = apex_domain(m.group(0).rstrip(".,);"))
        if apex and apex not in _HN_HOSTS:
            return apex
    for m in _BARE_RE.finditer(unescaped):
        cand = m.group(1).lower().rstrip(".")
        if cand.rsplit(".", 1)[-1] in _ALLOWED_TLDS:
            apex = apex_domain(cand)
            if apex and apex not in _HN_HOSTS:
                return apex
    return None


@register
class HNFreelanceCollector(BaseCollector):
    source_slug = "hn_freelance"
    collector_slug = "hn_freelance"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        # Default seed: the Algolia search for buyer requests, newest first (no key).
        self._seeds = seeds or [
            'https://hn.algolia.com/api/v1/search_by_date'
            '?query=%22seeking%20freelancer%22&tags=comment&hitsPerPage=100'
        ]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        hits = data.get("hits", []) if isinstance(data, dict) else []
        return ParsedDocument(url=raw.url, structured={"hits": hits})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for hit in doc.structured.get("hits", []):
            raw_text = hit.get("comment_text") or hit.get("story_text") or ""
            text = _clean(raw_text)
            # Buyers only: "SEEKING FREELANCER" comments (skip "SEEKING WORK" offers).
            if "seeking freelancer" not in text.lower():
                continue
            apex = _first_external_domain(raw_text)
            if not apex:
                continue  # no company link to anchor (anonymous post) — skip for now
            object_id = hit.get("objectID") or ""
            permalink = f"https://news.ycombinator.com/item?id={object_id}"
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": apex, "display_name": apex, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=permalink, claim_type="company.domain",
                                       snippet=text[:200], confidence=0.6),
                blocking_hints={"apex_domain": apex}))
            out.extend(detect_signals(text, permalink, apex))
        return out
