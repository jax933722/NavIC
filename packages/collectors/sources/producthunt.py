"""producthunt collector (spec 03 §7) — public launch data.

From Product Hunt posts it emits the launched company (via its website), a
product_launch signal, and the makers as people affiliated with the company
(they built and shipped it). Public data via the official API; honors ToS.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain
from parsing import ParsedDocument

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register


@register
class ProductHuntCollector(BaseCollector):
    source_slug = "producthunt"
    collector_slug = "producthunt"
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
        posts = data.get("posts", data if isinstance(data, list) else [])
        return ParsedDocument(url=raw.url, structured={"posts": posts})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for post in doc.structured.get("posts", []):
            website = post.get("website") or post.get("redirect_url") or ""
            apex = apex_domain(website)
            if not apex:
                continue
            name = post.get("name") or apex
            page = post.get("url") or website
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=page, claim_type="company.domain",
                                       snippet=post.get("tagline", "")[:200], confidence=0.7),
                blocking_hints={"apex_domain": apex}))
            out.append(build_candidate(
                kind="signal", signal_type="product_launch",
                attributes={"company_domain": apex, "intent_axis": "scaling",
                            "strength": 0.55, "product": name},
                evidence=EvidenceDraft(url=page, claim_type="signal.product_launch",
                                       snippet=f"Launched {name}: {post.get('tagline', '')}"[:200],
                                       confidence=0.7),
                blocking_hints={"apex_domain": apex}))
            for maker in post.get("makers", []):
                fullname = maker.get("name")
                if fullname:
                    out.append(build_candidate(
                        kind="entity", entity_type="person",
                        attributes={"full_name": fullname, "name": fullname,
                                    "current_role": maker.get("headline", "Maker"),
                                    "company_apex": apex, "company_domain": apex},
                        evidence=EvidenceDraft(url=page, claim_type="person.role",
                                               snippet=f"{fullname} made {name}", confidence=0.6),
                        blocking_hints={"name": fullname, "company_apex": apex}))
        return out
