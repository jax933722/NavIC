"""workable collector (spec 03 §7) — public Workable job board.

Reads a company's public Workable jobs (e.g. <account>.workable.com/spi/v3/jobs),
the JSON its careers page renders. Open roles are a structured hiring signal. The
operator pairs each account with the company website in config; the payload carries
it as `company`. Public data, no auth, no cost.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord
from ingestion import RawResponse
from parsing import ParsedDocument

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..jobboard import build_jobboard_candidates
from ..registry import register


def _location(job: dict) -> str | None:
    loc = job.get("location")
    if isinstance(loc, dict):
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        return ", ".join(p for p in parts if p) or None
    return loc


@register
class WorkableCollector(BaseCollector):
    source_slug = "workable"
    collector_slug = "workable"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

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
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        company = data.get("company", {}) if isinstance(data, dict) else {}
        return ParsedDocument(url=raw.url, structured={"company": company, "jobs": jobs})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        jobs = []
        for j in doc.structured.get("jobs", []):
            jobs.append({"title": j.get("title") or j.get("full_title", ""),
                         "department": j.get("department"),
                         "location": _location(j),
                         "url": j.get("url") or j.get("application_url")})
        return build_jobboard_candidates(doc.structured.get("company", {}), jobs)
