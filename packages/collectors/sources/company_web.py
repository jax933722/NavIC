"""company_web collector (spec 03 §7).

The M0 collector: from a company homepage it emits
  - a ``company`` entity (domain from the URL; name from og:site_name/title),
  - a weak ``hiring`` signal when the page hints at open roles (careers links or
    "we're hiring" text) — enough to seed a Bronze opportunity.
Every emitted claim carries evidence (invariant I2).
"""

from __future__ import annotations

from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain, normalize_company_name
from parsing import ParsedDocument, parse_html
from signals import classify_document

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register


@register
class CompanyWebCollector(BaseCollector):
    source_slug = "company_web"
    collector_slug = "company_web"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="standard")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or []

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=apex_domain(url) or url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        return parse_html(raw.body, raw.url)

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        apex = apex_domain(doc.url)
        if not apex:
            return []

        title_name = (doc.title or apex).split("|")[0].split("—")[0].strip()
        name = doc.meta.get("og:site_name") or title_name
        candidates: list[CandidateRecord] = [
            build_candidate(
                kind="entity",
                entity_type="company",
                attributes={
                    "name": name,
                    "display_name": name,
                    "primary_domain": apex,
                    "canonical_key": apex,
                },
                evidence=EvidenceDraft(
                    url=doc.url,
                    claim_type="company.domain",
                    snippet=(doc.title or name)[:280],
                    confidence=0.9,
                ),
                blocking_hints={"apex_domain": apex, "name": normalize_company_name(name)},
            )
        ]

        # Full signal classification (funding, hiring+department, tech, pain, launch).
        candidates.extend(classify_document(doc, apex))
        return candidates
