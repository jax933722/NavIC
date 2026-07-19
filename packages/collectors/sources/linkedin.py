"""linkedin collector (spec 03 §7) — AUTHORIZED / PUBLIC data only.

IMPORTANT (blueprint §25, spec 03: public-only, ToS honored): this collector does
NOT scrape the authenticated/auth-walled LinkedIn site — that violates LinkedIn's
Terms of Service and the platform's public-only rule. It ingests LinkedIn data the
operator is authorized to have: the official LinkedIn API (Marketing/Organization
endpoints under an approved app) or an authorized data export. The input is a
structured company payload; the collector never bypasses authentication or robots.

From an authorized company profile it emits the company (firmographics), listed
employees as people (works_at relationship), and hiring signals from open jobs.
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


def _department_for(title: str) -> str | None:
    low = (title or "").lower()
    for keyword, dept in DEPARTMENT_BY_ROLE.items():
        if keyword in low:
            return dept
    return None


@register
class LinkedInCollector(BaseCollector):
    source_slug = "linkedin"
    collector_slug = "linkedin"
    version = "0.1.0"
    # auth_kind=oauth: an approved LinkedIn app; NOT a logged-in session scraper.
    capabilities = Capabilities(supports_incremental=True, auth_kind="oauth",
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
        return ParsedDocument(url=raw.url, structured={"profile": data})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        profile = doc.structured.get("profile", {})
        company = profile.get("company", {})
        website = company.get("website") or ""
        apex = apex_domain(website)
        if not apex:
            return []
        page = company.get("linkedin_url") or website
        name = company.get("name") or apex
        slug = company.get("linkedin_slug")

        out: list[CandidateRecord] = [
            build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": apex,
                            "canonical_key": apex, "industry": company.get("industry"),
                            "employee_range": company.get("employee_range"),
                            "linkedin_slug": slug},
                evidence=EvidenceDraft(url=page, claim_type="company.domain",
                                       snippet=f"LinkedIn: {name}", confidence=0.85),
                blocking_hints={"apex_domain": apex, "linkedin_slug": slug}),
        ]
        for person in profile.get("people", []):
            fullname = person.get("name")
            if not fullname:
                continue
            out.append(build_candidate(
                kind="entity", entity_type="person",
                attributes={"full_name": fullname, "name": fullname,
                            "current_role": person.get("title"),
                            "linkedin_slug": person.get("linkedin_slug"),
                            "company_apex": apex, "company_domain": apex},
                evidence=EvidenceDraft(url=person.get("linkedin_url") or page,
                                       claim_type="person.role",
                                       snippet=f"{fullname} — {person.get('title', '')}"[:200],
                                       confidence=0.8),
                blocking_hints={"name": fullname, "company_apex": apex,
                                "linkedin_slug": person.get("linkedin_slug")}))
        for job in profile.get("jobs", []):
            dept = _department_for(job.get("title", ""))
            out.append(build_candidate(
                kind="signal", signal_type="hiring",
                attributes={"company_domain": apex, "intent_axis": "hiring",
                            "department": dept, "strength": 0.6, "weak": dept is None,
                            "role": job.get("title")},
                evidence=EvidenceDraft(url=job.get("url") or page, claim_type="signal.hiring",
                                       snippet=f"Hiring: {job.get('title', '')}"[:200],
                                       confidence=0.7),
                blocking_hints={"apex_domain": apex}))
        return out
