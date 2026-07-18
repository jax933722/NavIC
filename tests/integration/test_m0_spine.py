"""M0 exit-gate test (docs/specs/08 §M0).

Drives the whole spine end-to-end with a stubbed fetch client — no infra:
  seeded URL -> fetch -> raw persisted -> parse -> evidence -> company entity
  -> weak hiring signal -> Bronze opportunity with evidence.
Also asserts the enrich-never-replace invariant: a re-crawl does not duplicate.
"""

from __future__ import annotations

import collectors.sources  # noqa: F401  (registers company_web)
from collectors import CollectorRuntime
from collectors.registry import get_collector
from collectors.runtime import make_context
from core.eventbus import InMemoryEventBus
from ingestion import InMemoryRawStore, StubFetchClient
from opportunities import Tier
from pipeline import M0Pipeline
from storage.repositories import (
    InMemoryEntityRepo,
    InMemoryEvidenceRepo,
    InMemoryOpportunityRepo,
    InMemorySignalRepo,
)

HOMEPAGE = """
<html><head>
  <title>Acme Robotics — Industrial Automation</title>
  <meta property="og:site_name" content="Acme Robotics"/>
</head><body>
  <h1>We build robots.</h1>
  <nav><a href="/careers">Careers</a> — we're hiring across engineering!</nav>
</body></html>
"""

URL = "https://www.acme.com/"


def _run_collector(bus):
    collector = get_collector("company_web")
    collector._seeds = [URL]  # M0 seeding; scheduler owns this in M3
    fetch = StubFetchClient({URL: (200, "text/html", HOMEPAGE)})
    raw_store = InMemoryRawStore()
    ctx = make_context("company_web", fetch, raw_store, trace_id="test-trace")
    runtime = CollectorRuntime(collector, ctx, bus)
    return runtime.run(), raw_store


def _fresh_repos():
    return dict(
        entities=InMemoryEntityRepo(),
        evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(),
        opportunities=InMemoryOpportunityRepo(),
    )


def test_url_to_bronze_opportunity_with_evidence():
    bus = InMemoryEventBus()
    collect_result, raw_store = _run_collector(bus)

    # Raw persisted before parse, and raw.fetched emitted.
    assert collect_result.fetched == 1
    assert collect_result.raw_refs and raw_store.get(collect_result.raw_refs[0].key) is not None
    assert any(e.type == "raw.fetched" for e in bus.published)

    # Company entity + weak hiring signal candidates, each with evidence (I2).
    kinds = {(c.kind, c.entity_type or c.signal_type) for c in collect_result.candidates}
    assert ("entity", "company") in kinds
    assert ("signal", "hiring") in kinds
    assert all(c.evidence and c.evidence.url for c in collect_result.candidates)

    # Drive the pipeline.
    repos = _fresh_repos()
    pipe = M0Pipeline(**repos)
    ch = collect_result.raw_refs[0].content_hash
    result = pipe.ingest(collect_result.candidates, content_hash=ch)

    assert result.companies == 1
    assert result.signals == 1

    opps = repos["opportunities"].list()
    assert len(opps) == 1
    opp = opps[0]
    assert opp.tier == Tier.BRONZE.value
    assert opp.opportunity_score > 0
    assert opp.evidence_ids, "opportunity must carry evidence (invariant I2)"

    # Company resolved with the apex as canonical key.
    company = repos["entities"].get(opp.company_entity_id)
    assert company.attributes["primary_domain"] == "acme.com"

    # Transition recorded: (none) -> bronze.
    assert any(t.to_tier == "bronze" and t.from_tier is None for t in result.transitions)


def test_recrawl_enriches_not_duplicates():
    bus = InMemoryEventBus()
    collect_result, _ = _run_collector(bus)
    repos = _fresh_repos()
    pipe = M0Pipeline(**repos)

    ch = collect_result.raw_refs[0].content_hash
    pipe.ingest(collect_result.candidates, content_hash=ch)
    pipe.ingest(collect_result.candidates, content_hash=ch)  # re-crawl

    # One canonical company, one opportunity — no duplication (I1/I4).
    assert len(repos["opportunities"].list()) == 1
    company = repos["entities"].find_by_canonical("company", "acme.com")
    assert company is not None and company.version >= 2  # enriched (version bumped)


def test_second_fetch_same_bytes_is_deduped():
    bus = InMemoryEventBus()
    collector = get_collector("company_web")
    collector._seeds = [URL, URL]  # same URL twice
    fetch = StubFetchClient({URL: (200, "text/html", HOMEPAGE)})
    ctx = make_context("company_web", fetch, InMemoryRawStore(), trace_id="t")
    result = CollectorRuntime(collector, ctx, bus).run()
    assert result.fetched == 1
    assert result.skipped_dedupe == 1  # content-hash dedupe (spec 03 §4.4)
