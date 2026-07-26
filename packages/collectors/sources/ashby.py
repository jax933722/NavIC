"""ashby collector (spec 03 §7) — public Ashby job board.

Reads a company's public Ashby board (api.ashbyhq.com/posting-api/job-board/<org>),
the JSON its careers page renders. Open roles are a structured hiring signal. The
operator pairs each board with the company website in config; the payload carries it
as `company`. Public data, no auth, no cost.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord
from ingestion import RawResponse
from parsing import ParsedDocument

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..jobboard import build_jobboard_candidates, company_for
from ..registry import register


@register
class AshbyCollector(BaseCollector):
    source_slug = "ashby"
    collector_slug = "ashby"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or []
        self._company_for: dict = {}  # {url: {name, website, careers_url}} for live crawls

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        payload_company = data.get("company") if isinstance(data, dict) else None
        company = company_for(self, raw.url, payload_company)
        return ParsedDocument(url=raw.url, structured={"company": company, "jobs": jobs})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        jobs = []
        for j in doc.structured.get("jobs", []):
            jobs.append({"title": j.get("title", ""),
                         "department": j.get("department") or j.get("team"),
                         "location": j.get("location"),
                         "url": j.get("jobUrl") or j.get("applyUrl")})
        return build_jobboard_candidates(doc.structured.get("company", {}), jobs)
