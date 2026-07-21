"""hn_search collector (spec 03 §7) — "people posting requirements", no API key.

The key-less requirement firehose. Reddit's API needs an app (and payment for
commercial use); Hacker News' Algolia search API needs NONE — no key, no signup, no
throttling — so this is the reliable default for finding people who publicly stated a
need. It searches ALL of Hacker News for buying-intent phrasing ("looking for a
developer", "can anyone recommend a designer", "in the market for") and keeps only the
hits the classifier confirms are a real service request.

Each kept post becomes a lead: anchored on a company the post names (a link/domain in
the text) when there is one, else on the poster (hn/handle) so an individual's request
is still captured — with the requirement (service/budget/timeline/stack) extracted and
the HN permalink to reply to.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from urllib.parse import quote

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register
from ..textutil import company_slug, first_external_domain, strip_html
from .remoteok import NON_COMPANY_HOSTS

_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {
    "news.ycombinator.com", "ycombinator.com", "hn.algolia.com", "algolia.com"}
_SKIP_AUTHORS = {"", "[deleted]"}

# Requirement phrasing to search HN for (comments, most recent first).
_QUERIES = (
    "looking for a developer", "looking for a designer", "looking for a freelancer",
    "can anyone recommend a", "in the market for", "looking to hire a",
    "need a freelancer", "recommendations for a",
)


def _search_urls() -> list[str]:
    return [f"https://hn.algolia.com/api/v1/search?query={quote(q)}"
            f"&tags=comment&hitsPerPage=100" for q in _QUERIES]


@register
class HNSearchCollector(BaseCollector):
    source_slug = "hn_search"
    collector_slug = "hn_search"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or _search_urls()

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
            raw_text = hit.get("comment_text") or hit.get("story_text") or hit.get("title") or ""
            text = strip_html(raw_text)
            if not text:
                continue
            object_id = hit.get("objectID") or ""
            permalink = f"https://news.ycombinator.com/item?id={object_id}"
            # Anchor on a company the post names, else on the poster.
            apex = first_external_domain(f"{hit.get('url', '')} {raw_text}",
                                         exclude=_EXCLUDE_HOSTS)
            if apex:
                anchor, kind, name = apex, "domain", apex
            else:
                author = (hit.get("author") or "").strip()
                if author.lower() in _SKIP_AUTHORS:
                    continue
                anchor, kind, name = company_slug(author), "name", f"hn/{author}"
                if not anchor:
                    continue
            signals = detect_signals(text, permalink, anchor)
            if not any(s.signal_type == "solicitation" for s in signals):
                continue
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": anchor,
                            "canonical_key": anchor, "anchor_kind": kind},
                evidence=EvidenceDraft(url=permalink, claim_type="company.domain",
                                       snippet=text[:200], confidence=0.55),
                blocking_hints={"apex_domain": anchor}))
            out.extend(signals)
        return out
