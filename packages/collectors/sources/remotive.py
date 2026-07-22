"""remotive collector (spec 03 §7) — public Remotive remote-jobs API, no key.

Reads Remotive's free public API (https://remotive.com/api/remote-jobs), a broad
firehose of remote roles across thousands of companies — including contract/freelance
gigs. Emits the hiring company + a hiring signal per role (and any service request the
description states, via the classifier). No auth, no cost.

Anchoring: the API gives a company NAME (and sometimes a URL in the description) but
not a reliable company domain. We take the domain from a link in the description when
there is one; otherwise we keep the lead by anchoring on the company name (marked so
the UI shows no website).
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

_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {"remotive.com", "remotive.io"}


@register
class RemotiveCollector(BaseCollector):
    source_slug = "remotive"
    collector_slug = "remotive"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or [
            "https://remotive.com/api/remote-jobs?category=software-dev",
            "https://remotive.com/api/remote-jobs?category=design",
            "https://remotive.com/api/remote-jobs?category=marketing",
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
        jobs = [j for j in jobs if isinstance(j, dict) and j.get("title")]
        return ParsedDocument(url=raw.url, structured={"jobs": jobs})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for job in doc.structured.get("jobs", []):
            title = job.get("title", "")
            company = job.get("company_name") or ""
            desc = job.get("description", "")
            apex = first_external_domain(f"{job.get('company_url', '')} {desc}",
                                         exclude=_EXCLUDE_HOSTS)
            # Anchor on a real domain if we found one, else on the company name.
            anchor, anchor_kind = (apex, "domain") if apex \
                else (company_slug(company), "name")
            if not anchor:
                continue
            name = company or apex or anchor
            evidence_url = job.get("url") or (f"https://{apex}" if apex else "https://remotive.com")
            dept = department_for(title, job.get("category"))
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": anchor,
                            "canonical_key": anchor, "anchor_kind": anchor_kind},
                evidence=EvidenceDraft(url=evidence_url, claim_type="company.domain",
                                       snippet=f"{name} — {title}"[:200], confidence=0.6),
                blocking_hints={"apex_domain": anchor}))
            out.append(build_candidate(
                kind="signal", signal_type="hiring",
                attributes={"company_domain": anchor, "intent_axis": "hiring", "department": dept,
                            "strength": 0.6, "weak": dept is None, "role": title,
                            "location": job.get("candidate_required_location") or "Remote"},
                evidence=EvidenceDraft(url=evidence_url, claim_type="signal.hiring",
                                       snippet=f"Hiring (remote): {title}"[:200], confidence=0.65),
                blocking_hints={"apex_domain": anchor}))
            out.extend(detect_signals(f"{title}. {desc}", evidence_url, anchor))
        return out
