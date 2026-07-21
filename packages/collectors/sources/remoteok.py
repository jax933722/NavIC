"""remoteok collector (spec 03 §7) — public RemoteOK jobs API.

Reads RemoteOK's free public API (https://remoteok.com/api), a broad firehose of
remote roles across thousands of companies — including contract/freelance gigs.
Emits the hiring company + a hiring signal per role (and any service request the
text states, via the classifier). No auth, no cost.

Anchoring: aggregators give a company NAME but not its domain, and our leads are
domain-anchored. So we take the company domain from the job's apply URL, skipping
RemoteOK's own host and the ATS hosts (which aren't the company's site); a role we
can't anchor to a real company domain is skipped.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..jobboard import department_for
from ..registry import register
from ..textutil import first_external_domain

# Aggregator + applicant-tracking hosts that are never the company's own domain.
NON_COMPANY_HOSTS = {
    "remoteok.com", "remoteok.io", "weworkremotely.com", "remotive.com", "remotive.io",
    "boards.greenhouse.io", "greenhouse.io", "jobs.lever.co", "lever.co",
    "jobs.ashbyhq.com", "ashbyhq.com", "workable.com", "apply.workable.com",
    "linkedin.com", "indeed.com", "glassdoor.com", "google.com",
}


@register
class RemoteOKCollector(BaseCollector):
    source_slug = "remoteok"
    collector_slug = "remoteok"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or ["https://remoteok.com/api"]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = []
        # RemoteOK's first array element is a legal/metadata notice — keep real jobs.
        jobs = [j for j in data if isinstance(j, dict) and j.get("position")] \
            if isinstance(data, list) else []
        return ParsedDocument(url=raw.url, structured={"jobs": jobs})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for job in doc.structured.get("jobs", []):
            links = f"{job.get('apply_url', '')} {job.get('company_url', '')} {job.get('url', '')}"
            apex = first_external_domain(links, exclude=NON_COMPANY_HOSTS)
            if not apex:
                continue
            title = job.get("position", "")
            company = job.get("company") or apex
            evidence_url = job.get("url") or job.get("apply_url") or f"https://{apex}"
            dept = department_for(title, None)
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": company, "display_name": company, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=evidence_url, claim_type="company.domain",
                                       snippet=f"{company} — {title}"[:200], confidence=0.6),
                blocking_hints={"apex_domain": apex}))
            out.append(build_candidate(
                kind="signal", signal_type="hiring",
                attributes={"company_domain": apex, "intent_axis": "hiring", "department": dept,
                            "strength": 0.6, "weak": dept is None, "role": title,
                            "location": job.get("location") or "Remote"},
                evidence=EvidenceDraft(url=evidence_url, claim_type="signal.hiring",
                                       snippet=f"Hiring (remote): {title}"[:200], confidence=0.65),
                blocking_hints={"apex_domain": apex}))
            # Also surface an explicit service request in the description, if any.
            out.extend(detect_signals(f"{title}. {job.get('description', '')}", evidence_url, apex))
        return out
