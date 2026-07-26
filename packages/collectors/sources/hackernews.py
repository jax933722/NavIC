"""hackernews collector (spec 03 §7) — public API, JSON stories.

From HN stories it emits the company the story is about (via the story URL) and
any buying signals in the title/text. Authors are NOT linked as employees (an HN
poster is not a company insider), avoiding false relationship edges.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register


@register
class HackerNewsCollector(BaseCollector):
    source_slug = "hackernews"
    collector_slug = "hackernews"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or []

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            items = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            items = []
        if isinstance(items, dict):
            items = [items]
        return ParsedDocument(url=raw.url, structured={"items": items})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for story in doc.structured.get("items", []):
            url = story.get("url")
            if not url:
                continue
            apex = apex_domain(url)
            if not apex:
                continue
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": apex, "display_name": apex, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=url, claim_type="company.domain",
                                       snippet=story.get("title", "")[:200], confidence=0.6),
                blocking_hints={"apex_domain": apex}))
            text = f"{story.get('title', '')}. {story.get('text', '')}"
            out.extend(detect_signals(text, url, apex))
        return out
