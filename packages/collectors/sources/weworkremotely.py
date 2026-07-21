"""weworkremotely collector (spec 03 §7) — public We Work Remotely RSS feeds.

Reads WWR's free public RSS (e.g. https://weworkremotely.com/remote-jobs.rss or a
category feed). Broad remote-hiring coverage. Titles are "Company: Role"; the
company domain is parsed from the item's linked apply URL (skipping WWR + ATS
hosts), and a role we can't anchor to a real company domain is skipped.
No auth, no cost.
"""

from __future__ import annotations

from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from parsing import ParsedDocument, parse_rss
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..jobboard import department_for
from ..registry import register
from ..textutil import first_external_domain
from .remoteok import NON_COMPANY_HOSTS


@register
class WeWorkRemotelyCollector(BaseCollector):
    source_slug = "weworkremotely"
    collector_slug = "weworkremotely"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="standard")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or [
            "https://weworkremotely.com/remote-jobs.rss",
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-design-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
            "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss",
            "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
        ]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        items = parse_rss(raw.body)
        return ParsedDocument(url=raw.url, structured={"items": [i.__dict__ for i in items]})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for item in doc.structured.get("items", []):
            title = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", "")
            # "Company: Role" — split once; fall back to the whole title as the role.
            company_name, _, role = title.partition(":")
            role = (role or company_name).strip()
            company_name = company_name.strip()
            apex = first_external_domain(f"{summary} {link}", exclude=NON_COMPANY_HOSTS)
            if not apex:
                continue
            company = company_name or apex
            dept = department_for(role, None)
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": company, "display_name": company, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=link or f"https://{apex}", claim_type="company.domain",
                                       snippet=title[:200], confidence=0.6),
                blocking_hints={"apex_domain": apex}))
            out.append(build_candidate(
                kind="signal", signal_type="hiring",
                attributes={"company_domain": apex, "intent_axis": "hiring", "department": dept,
                            "strength": 0.6, "weak": dept is None, "role": role,
                            "location": "Remote"},
                evidence=EvidenceDraft(url=link or f"https://{apex}", claim_type="signal.hiring",
                                       snippet=f"Hiring (remote): {role}"[:200], confidence=0.65),
                blocking_hints={"apex_domain": apex}))
            out.extend(detect_signals(f"{role}. {summary}", link or f"https://{apex}", apex))
        return out
