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

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register
from ..textutil import first_external_domain, strip_html

_HN_HOSTS = {"news.ycombinator.com", "ycombinator.com", "hn.algolia.com", "algolia.com"}


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
            text = strip_html(raw_text)
            # Buyers only: "SEEKING FREELANCER" comments (skip "SEEKING WORK" offers).
            if "seeking freelancer" not in text.lower():
                continue
            apex = first_external_domain(raw_text, exclude=_HN_HOSTS)
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
