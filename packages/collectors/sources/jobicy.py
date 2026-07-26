"""jobicy collector (spec 03 §7) — Jobicy remote-jobs API, no key.

Jobicy publishes a free, key-less public API (https://jobicy.com/api/v2/remote-jobs)
of remote roles across many companies. Each open role is a hiring signal (buying
intent); the classifier also lifts any explicit service request. No auth, no cost.

Anchoring: the API gives a company NAME (and sometimes a domain in the description),
so we anchor on a domain when we find one, else on the company name (name-only).
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
from ..textutil import company_slug, first_external_domain
from .remoteok import NON_COMPANY_HOSTS

_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {"jobicy.com"}


@register
class JobicyCollector(BaseCollector):
    source_slug = "jobicy"
    collector_slug = "jobicy"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or [
            "https://jobicy.com/api/v2/remote-jobs?count=50",
            "https://jobicy.com/api/v2/remote-jobs?count=50&industry=design",
            "https://jobicy.com/api/v2/remote-jobs?count=50&industry=marketing",
        ]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        jobs = [j for j in jobs if isinstance(j, dict) and j.get("jobTitle")]
        return ParsedDocument(url=raw.url, structured={"jobs": jobs})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for job in doc.structured.get("jobs", []):
            title = job.get("jobTitle", "")
            company = job.get("companyName") or ""
            desc = job.get("jobDescription", "")
            page = job.get("url") or "https://jobicy.com"
            apex = first_external_domain(desc, exclude=_EXCLUDE_HOSTS)
            anchor, anchor_kind = (apex, "domain") if apex else (company_slug(company), "name")
            if not anchor:
                continue
            name = company or apex or anchor
            industry = job.get("jobIndustry")
            category = industry[0] if isinstance(industry, list) and industry else None
            dept = department_for(title, category)
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": anchor,
                            "canonical_key": anchor, "anchor_kind": anchor_kind},
                evidence=EvidenceDraft(url=page, claim_type="company.domain",
                                       snippet=f"{name} — {title}"[:200], confidence=0.6),
                blocking_hints={"apex_domain": anchor}))
            out.append(build_candidate(
                kind="signal", signal_type="hiring",
                attributes={"company_domain": anchor, "intent_axis": "hiring", "department": dept,
                            "strength": 0.6, "weak": dept is None, "role": title,
                            "location": job.get("jobGeo") or "Remote"},
                evidence=EvidenceDraft(url=page, claim_type="signal.hiring",
                                       snippet=f"Hiring (remote): {title}"[:200], confidence=0.65),
                blocking_hints={"apex_domain": anchor}))
            out.extend(detect_signals(f"{title}. {desc}", page, anchor))
        return out
