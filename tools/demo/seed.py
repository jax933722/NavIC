"""Seed a NavIC pipeline with self-contained multi-source sample data.

Runs each bundled collector over a small sample payload (tools/demo/data/*.json)
with a StubFetchClient — no external network — and drives the candidates through
the same M0 pipeline the API serves. The result is a realistic board spanning all
maturity tiers (Gold / Silver / Bronze) drawn from every source type, which is
exactly what the local Docker demo shows.

The sample data is a static snapshot for demonstration only; production data comes
from the live collectors on their schedule.
"""

from __future__ import annotations

import json
from pathlib import Path

import collectors.sources  # noqa: F401  (register all collectors)
from collectors import CollectorRuntime
from collectors.registry import get_collector
from collectors.runtime import make_context
from core.eventbus import InMemoryEventBus
from ingestion import InMemoryRawStore, StubFetchClient

DATA = Path(__file__).resolve().parent / "data"

# (collector slug, sample file). The URL is synthetic — the stub returns the file.
SAMPLES = [
    ("funding", "funding.json"),
    ("greenhouse", "greenhouse.json"),
    ("news", "news.json"),
    ("reddit", "reddit.json"),
    ("producthunt", "producthunt.json"),
    ("linkedin", "linkedin.json"),
    # LinkedIn posts where the author publicly asks for a vendor — solicitation
    # buying signals, which become Gold opportunities (person + role + company + ask).
    # linkedin_social = a Shopify design request; linkedin_devservices = an
    # e-commerce build with a stated budget + timeline (extracted onto the signal).
    ("linkedin", "linkedin_social.json"),
    ("linkedin", "linkedin_devservices.json"),
    ("github_org", "github.json"),
    ("hackernews", "hackernews.json"),
]

# A funding round on the same domain as the LinkedIn company (Wayne Analytics).
# Entity resolution merges them by domain, so the company gains both a funding
# signal (satisfies an opportunity template) and a VP-of-Sales works_at edge —
# the combination that qualifies a Gold opportunity.
GOLD_FUNDING = json.dumps({"rounds": [{
    "company": {"name": "Wayne Analytics", "website": "https://wayne-analytics.com"},
    "round": "Series C", "amount_usd": 90000000, "investors": ["Sequoia", "Kleiner"],
    "announced_on": "2026-07-10", "url": "https://fundingnews.example/wayne-series-c"}]})


def _ingest(pipeline, slug: str, body: str, totals: dict) -> None:
    url = f"https://demo.local/{slug}"
    collector = get_collector(slug)
    collector._seeds = [url]
    fetch = StubFetchClient({url: (200, "application/json", body)})
    ctx = make_context(collector.source_slug, fetch, InMemoryRawStore(), trace_id="demo-seed")
    collected = CollectorRuntime(collector, ctx, InMemoryEventBus()).run()
    run_hash = collected.raw_refs[0].content_hash if collected.raw_refs else slug
    result = pipeline.ingest(collected.candidates, content_hash=run_hash)
    totals["companies"] += result.companies
    totals["signals"] += result.signals
    totals["opportunities"] += len(result.opportunities)


def seed(pipeline) -> dict:
    """Populate the given M0 pipeline's repositories with the demo dataset."""
    totals = {"companies": 0, "signals": 0, "opportunities": 0}
    for slug, filename in SAMPLES:
        _ingest(pipeline, slug, (DATA / filename).read_text(), totals)
    _ingest(pipeline, "funding", GOLD_FUNDING, totals)
    return totals
