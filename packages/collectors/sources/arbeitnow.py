"""arbeitnow collector (spec 03 §7) — Arbeitnow job-board API, no key.

Arbeitnow publishes a free, key-less public job-board API
(https://www.arbeitnow.com/api/job-board-api) spanning many companies (strong in the
EU). Each open role is a hiring signal (buying intent); the classifier also lifts any
explicit service request. No auth, no cost.

Anchoring: the API gives a company NAME (and sometimes a domain in the description), so
we anchor on a domain when we find one, else on the company name (name-only).
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

_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {"arbeitnow.com"}


@register
class ArbeitnowCollector(BaseCollector):
    source_slug = "arbeitnow"
    collector_slug = "arbeitnow"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or ["https://www.arbeitnow.com/api/job-board-api"]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        jobs = data.get("data", []) if isinstance(data, dict) else []
        jobs = [j for j in jobs if isinstance(j, dict) and j.get("title")]
        return ParsedDocument(url=raw.url, structured={"jobs": jobs})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for job in doc.structured.get("jobs", []):
            title = job.get("title", "")
            company = job.get("company_name") or ""
            desc = job.get("description", "")
            page = job.get("url") or "https://www.arbeitnow.com"
            apex = first_external_domain(desc, exclude=_EXCLUDE_HOSTS)
            anchor, anchor_kind = (apex, "domain") if apex else (company_slug(company), "name")
            if not anchor:
                continue
            name = company or apex or anchor
            tags = job.get("tags") or []
            category = tags[0] if isinstance(tags, list) and tags and isinstance(tags[0], str) \
                else None
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
                            "location": job.get("location") or ("Remote" if job.get("remote")
                                                                else None)},
                evidence=EvidenceDraft(url=page, claim_type="signal.hiring",
                                       snippet=f"Hiring: {title}"[:200], confidence=0.65),
                blocking_hints={"apex_domain": anchor}))
            out.extend(detect_signals(f"{title}. {desc}", page, anchor))
        return out
