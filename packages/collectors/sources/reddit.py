"""reddit collector (spec 03 §7) — public listing JSON.

Consumes Reddit's public listing format (e.g. https://www.reddit.com/r/<sub>/.json,
or the official API). From posts it emits the company a post links to (via the
external URL) and any buying signals in the title/self-text. Post authors are NOT
linked as employees (a Redditor is not a company insider). Public data only;
honors Reddit's API terms and rate limits.
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

_SELF_HOSTS = {"reddit.com", "redd.it", "redditmedia.com"}


@register
class RedditCollector(BaseCollector):
    source_slug = "reddit"
    collector_slug = "reddit"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="standard")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or []

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        root = data.get("data", {}) or {} if isinstance(data, dict) else {}
        children = root.get("children", [])
        posts = [c.get("data", {}) for c in children if isinstance(c, dict)]
        return ParsedDocument(url=raw.url, structured={"posts": posts})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for post in doc.structured.get("posts", []):
            url = post.get("url_overridden_by_dest") or post.get("url") or ""
            apex = apex_domain(url)
            title = post.get("title", "")
            body = post.get("selftext", "")
            permalink = "https://www.reddit.com" + post.get("permalink", "")
            if apex and apex not in _SELF_HOSTS:
                out.append(build_candidate(
                    kind="entity", entity_type="company",
                    attributes={"name": apex, "display_name": apex, "primary_domain": apex,
                                "canonical_key": apex},
                    evidence=EvidenceDraft(url=url, claim_type="company.domain",
                                           snippet=title[:200], confidence=0.55),
                    blocking_hints={"apex_domain": apex}))
                out.extend(detect_signals(f"{title}. {body}", permalink or url, apex))
        return out
