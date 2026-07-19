"""news collector (spec 03 §7) — public news monitoring.

Consumes a news feed whose articles have already been tagged with the SUBJECT
company (name + website) — the shape returned by entity-tagged news APIs and
news-alert feeds. This matters: a news article's own URL is the *publisher's*
domain (e.g. a tech-press site), never the company the article is about, so we
must not derive the company from the article link. The subject company comes
from the article's tagged company field; the article URL is kept only as
evidence. Buying signals (funding, launches, hiring, churn) are detected from
the headline and description.

Public data only; honors each publisher's terms and robots.
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
class NewsCollector(BaseCollector):
    source_slug = "news"
    collector_slug = "news"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, auth_kind="api_key",
                                politeness_class="aggressive-with-api")

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
        articles = data.get("articles", data if isinstance(data, list) else [])
        return ParsedDocument(url=raw.url, structured={"articles": articles})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for article in doc.structured.get("articles", []):
            company = article.get("company") or {}
            website = company.get("website") or company.get("domain") or ""
            apex = apex_domain(website)
            if not apex:
                continue
            name = company.get("name") or apex
            title = article.get("title", "")
            description = article.get("description") or article.get("content") or ""
            # Evidence links to the article; the company is the tagged subject.
            article_url = article.get("url") or website
            publisher = (article.get("source") or {}).get("name") if isinstance(
                article.get("source"), dict) else article.get("source")
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(
                    url=article_url, claim_type="company.domain",
                    snippet=f"{title} ({publisher})"[:200] if publisher else title[:200],
                    confidence=0.6),
                blocking_hints={"apex_domain": apex}))
            out.extend(detect_signals(f"{title}. {description}", article_url, apex))
        return out
