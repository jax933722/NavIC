"""rss_blog collector (spec 03 §7).

Proves the framework's core promise: a structurally different source (an XML feed,
not an HTML page) is added with ONLY this module + @register — zero core changes.
From a company blog feed it emits the company, each post, post authors (people
with relationship context), and any signals detected in titles/summaries.
"""

from __future__ import annotations

from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain
from parsing import ParsedDocument, parse_rss
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register


@register
class RssBlogCollector(BaseCollector):
    source_slug = "company_web"
    collector_slug = "rss_blog"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="standard")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or []

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=apex_domain(url) or url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        items = parse_rss(raw.body)
        return ParsedDocument(
            url=raw.url,
            structured={"items": [item.__dict__ for item in items]},
        )

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        apex = apex_domain(doc.url)
        if not apex:
            return []
        out: list[CandidateRecord] = [
            build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": apex, "display_name": apex, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=doc.url, claim_type="company.domain",
                                       snippet=f"Blog feed for {apex}", confidence=0.7),
                blocking_hints={"apex_domain": apex},
            )
        ]
        for item in doc.structured.get("items", []):
            url = item.get("link") or doc.url
            title = item.get("title", "")
            summary = item.get("summary", "")
            out.append(build_candidate(
                kind="entity", entity_type="post",
                attributes={"title": title, "url": url, "published": item.get("published"),
                            "company_domain": apex},
                evidence=EvidenceDraft(url=url, claim_type="post.published",
                                       snippet=title[:200], confidence=0.85),
                blocking_hints={"apex_domain": apex},
            ))
            if item.get("author"):
                out.append(build_candidate(
                    kind="entity", entity_type="person",
                    attributes={"full_name": item["author"], "name": item["author"],
                                "current_role": "Author", "company_apex": apex,
                                "company_domain": apex},
                    evidence=EvidenceDraft(url=url, claim_type="person.authored",
                                           snippet=f"{item['author']} wrote: {title[:120]}",
                                           confidence=0.6),
                    blocking_hints={"name": item["author"], "company_apex": apex},
                ))
            # Signals from post title + summary.
            out.extend(detect_signals(f"{title}. {summary}", url, apex))
        return out
