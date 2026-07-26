"""funding collector (spec 03 §7) — structured funding-round feed.

Consumes a feed of funding-round announcements (the shape published by funding
databases and round-tracking newsletters/APIs). Each round already identifies the
company (name + website), the stage, amount, investors, and a source article, so
this emits a high-confidence, richly-attributed funding_raised signal — stronger
and more precise than the regex funding detector, which only sees prose. Fresh
capital is a top-tier buying trigger: newly funded companies scale headcount and
tooling. Emits the company plus one funding_raised signal per round.

Public data only; every round links back to its public source.
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

# Later stages imply more aggressive scaling -> a stronger buying signal.
_STAGE_STRENGTH = {
    "pre-seed": 0.55, "seed": 0.65, "series a": 0.75, "series b": 0.8,
    "series c": 0.82, "series d": 0.82, "growth": 0.8,
}


def _amount_usd(round_: dict) -> float | None:
    val = round_.get("amount_usd", round_.get("amount"))
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


@register
class FundingCollector(BaseCollector):
    source_slug = "funding"
    collector_slug = "funding"
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
        rounds = data.get("rounds", data if isinstance(data, list) else [])
        return ParsedDocument(url=raw.url, structured={"rounds": rounds})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for round_ in doc.structured.get("rounds", []):
            company = round_.get("company") or {}
            website = company.get("website") or company.get("domain") or ""
            apex = apex_domain(website)
            if not apex:
                continue
            name = company.get("name") or apex
            stage = (round_.get("round") or round_.get("stage") or "").strip()
            amount = _amount_usd(round_)
            investors = round_.get("investors") or []
            source_url = round_.get("url") or round_.get("source_url") or website
            strength = _STAGE_STRENGTH.get(stage.lower(), 0.7)

            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=source_url, claim_type="company.domain",
                                       snippet=f"{name} raised {stage}".strip(), confidence=0.8),
                blocking_hints={"apex_domain": apex}))

            amount_str = f"${amount:,.0f}" if amount is not None else "undisclosed"
            snippet = f"{name} raised a {stage or 'funding'} round ({amount_str})"
            out.append(build_candidate(
                kind="signal", signal_type="funding_raised",
                attributes={"company_domain": apex, "intent_axis": "growth",
                            "strength": strength, "round": stage or None,
                            "amount_usd": amount, "investors": investors,
                            "announced_on": round_.get("announced_on")},
                evidence=EvidenceDraft(url=source_url, claim_type="signal.funding_raised",
                                       snippet=snippet[:280], confidence=0.85),
                blocking_hints={"apex_domain": apex}))
        return out
