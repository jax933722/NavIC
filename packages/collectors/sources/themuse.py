"""themuse collector (spec 03 §7) — The Muse public jobs API, no key.

The Muse publishes an official, key-less public jobs API
(https://www.themuse.com/api/public/jobs) spanning thousands of companies. Each open
role is a hiring signal (buying intent); the classifier also lifts any explicit service
request in the text. No auth, no cost.

Anchoring: the API gives a company NAME but not a domain, so we anchor on a domain found
in the role text when there is one, else on the company name (marked name-only).
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

_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {"themuse.com"}


@register
class TheMuseCollector(BaseCollector):
    source_slug = "themuse"
    collector_slug = "themuse"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or [
            "https://www.themuse.com/api/public/jobs?page=0",
            "https://www.themuse.com/api/public/jobs?category=Design&page=0",
        ]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        results = data.get("results", []) if isinstance(data, dict) else []
        results = [j for j in results if isinstance(j, dict) and j.get("name")]
        return ParsedDocument(url=raw.url, structured={"results": results})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for job in doc.structured.get("results", []):
            title = job.get("name", "")
            company = (job.get("company") or {}).get("name") or ""
            page = (job.get("refs") or {}).get("landing_page") or "https://www.themuse.com"
            desc = job.get("contents", "")
            apex = first_external_domain(desc, exclude=_EXCLUDE_HOSTS)
            anchor, anchor_kind = (apex, "domain") if apex else (company_slug(company), "name")
            if not anchor:
                continue
            name = company or apex or anchor
            cats = job.get("categories") or []
            category = cats[0].get("name") if cats and isinstance(cats[0], dict) else None
            dept = department_for(title, category)
            locs = job.get("locations") or []
            location = locs[0].get("name") if locs and isinstance(locs[0], dict) else None
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
                            "location": location},
                evidence=EvidenceDraft(url=page, claim_type="signal.hiring",
                                       snippet=f"Hiring: {title}"[:200], confidence=0.65),
                blocking_hints={"apex_domain": anchor}))
            out.extend(detect_signals(f"{title}. {desc}", page, anchor))
        return out
