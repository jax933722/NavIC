"""greenhouse collector (spec 03 §7) — public job-board API.

Consumes a company's public Greenhouse board (boards-api.greenhouse.io) — the same
JSON any visitor sees on the company's careers page. Open roles are a strong,
structured hiring signal: they reveal which departments a company is scaling and
therefore what they may be in-market to buy. Emits the company plus one hiring
signal per open role, with the department inferred from the role's own
department field (preferred) or its title.

Public data only; honors the board API's terms and rate limits.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain
from parsing import ParsedDocument
from signals.taxonomy import DEPARTMENT_BY_ROLE

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register


def _department_for(title: str, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    low = (title or "").lower()
    for keyword, dept in DEPARTMENT_BY_ROLE.items():
        if keyword in low:
            return dept
    return None


@register
class GreenhouseCollector(BaseCollector):
    source_slug = "greenhouse"
    collector_slug = "greenhouse"
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
        return ParsedDocument(url=raw.url, structured={"board": data})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        board = doc.structured.get("board", {})
        company = board.get("company", {})
        website = company.get("website") or ""
        apex = apex_domain(website)
        if not apex:
            return []
        name = company.get("name") or apex
        page = company.get("careers_url") or website

        out: list[CandidateRecord] = [
            build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=page, claim_type="company.domain",
                                       snippet=f"Careers: {name}", confidence=0.75),
                blocking_hints={"apex_domain": apex}),
        ]
        jobs = board.get("jobs", [])
        for job in jobs:
            title = job.get("title", "")
            departments = job.get("departments") or []
            explicit = departments[0].get("name") if departments else job.get("department")
            dept = _department_for(title, explicit)
            location = (job.get("location") or {}).get("name") if isinstance(
                job.get("location"), dict) else job.get("location")
            out.append(build_candidate(
                kind="signal", signal_type="hiring",
                attributes={"company_domain": apex, "intent_axis": "hiring",
                            "department": dept, "strength": 0.65, "weak": dept is None,
                            "role": title, "location": location},
                evidence=EvidenceDraft(
                    url=job.get("absolute_url") or job.get("url") or page,
                    claim_type="signal.hiring",
                    snippet=f"Open role: {title}"[:200], confidence=0.75),
                blocking_hints={"apex_domain": apex}))
        # Sustained hiring across many roles is a scaling signal in its own right.
        if len(jobs) >= 5:
            out.append(build_candidate(
                kind="signal", signal_type="expansion",
                attributes={"company_domain": apex, "intent_axis": "scaling",
                            "strength": 0.6, "open_roles": len(jobs)},
                evidence=EvidenceDraft(url=page, claim_type="signal.expansion",
                                       snippet=f"{len(jobs)} open roles at {name}",
                                       confidence=0.65),
                blocking_hints={"apex_domain": apex}))
        return out
