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

from extraction import CandidateRecord
from ingestion import RawResponse
from parsing import ParsedDocument

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..jobboard import build_jobboard_candidates, company_for
from ..registry import register


@register
class GreenhouseCollector(BaseCollector):
    source_slug = "greenhouse"
    collector_slug = "greenhouse"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, auth_kind="api_key",
                                politeness_class="aggressive-with-api")

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
        return ParsedDocument(url=raw.url, structured={"board": data})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        board = doc.structured.get("board", {})
        jobs = []
        for job in board.get("jobs", []):
            departments = job.get("departments") or []
            explicit = departments[0].get("name") if departments else job.get("department")
            location = (job.get("location") or {}).get("name") if isinstance(
                job.get("location"), dict) else job.get("location")
            jobs.append({"title": job.get("title", ""), "department": explicit,
                         "location": location, "url": job.get("absolute_url") or job.get("url")})
        return build_jobboard_candidates(company_for(self, doc.url, board.get("company")), jobs)
