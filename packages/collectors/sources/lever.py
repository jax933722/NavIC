"""lever collector (spec 03 §7) — public Lever job board.

Reads a company's public Lever postings (api.lever.co/v0/postings/<token>?mode=json),
the same JSON the careers page renders. Open roles are a structured hiring signal.
The operator pairs each board token with the company website in config; the fetched
payload carries it as `company`. Public data, no auth, no cost.
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
class LeverCollector(BaseCollector):
    source_slug = "lever"
    collector_slug = "lever"
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
        # Lever returns a bare array of postings; company comes from the payload
        # (fixtures) or the operator-configured company for this URL (live).
        postings = data.get("postings", data if isinstance(data, list) else [])
        payload_company = data.get("company") if isinstance(data, dict) else None
        company = company_for(self, raw.url, payload_company)
        return ParsedDocument(url=raw.url, structured={"company": company, "postings": postings})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        jobs = []
        for p in doc.structured.get("postings", []):
            cats = p.get("categories") or {}
            jobs.append({"title": p.get("text", ""),
                         "department": cats.get("team") or cats.get("department"),
                         "location": cats.get("location"),
                         "url": p.get("hostedUrl") or p.get("applyUrl")})
        return build_jobboard_candidates(doc.structured.get("company", {}), jobs)
