"""Thin orchestrator shared by the API seed endpoint and the seed CLI.

Runs the company_web collector over a set of URLs and drives the resulting
candidates through the M0 pipeline. The fetch client is injected so callers use
a real httpx client in production and a stub in tests.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.eventbus import EventBus, InMemoryEventBus
from ingestion import FetchClient, InMemoryRawStore, RawStore

from .m0 import M0Pipeline, PipelineResult


@dataclass
class IngestSummary:
    fetched: int
    companies: int
    signals: int
    opportunities: int
    transitions: int


def ingest_company_web_urls(
    urls: list[str],
    *,
    pipeline: M0Pipeline,
    fetch: FetchClient,
    raw_store: RawStore | None = None,
    bus: EventBus | None = None,
) -> IngestSummary:
    # Imported here to avoid a core->collectors import cycle at module load.
    import collectors.sources  # noqa: F401  (ensures company_web is registered)
    from collectors import CollectorRuntime
    from collectors.registry import get_collector
    from collectors.runtime import make_context

    bus = bus or InMemoryEventBus()
    raw_store = raw_store or InMemoryRawStore()

    collector = get_collector("company_web")
    collector._seeds = list(urls)  # M0 seeding; the scheduler owns this in M3
    ctx = make_context("company_web", fetch, raw_store)
    collected = CollectorRuntime(collector, ctx, bus).run()

    run_hash = collected.raw_refs[0].content_hash if collected.raw_refs else ""
    result: PipelineResult = pipeline.ingest(collected.candidates, content_hash=run_hash)
    return IngestSummary(
        fetched=collected.fetched,
        companies=result.companies,
        signals=result.signals,
        opportunities=len(result.opportunities),
        transitions=len(result.transitions),
    )
