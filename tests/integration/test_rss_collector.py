"""M3: the rss_blog collector — a structurally different source (XML feed) added
with zero core changes. Golden-fixture driven (spec 09 §3.2)."""

from __future__ import annotations

from pathlib import Path

import collectors.sources  # noqa: F401
from collectors import CollectorRuntime
from collectors.registry import get_collector
from collectors.runtime import make_context
from core.eventbus import InMemoryEventBus
from ingestion import InMemoryRawStore, StubFetchClient
from opportunities import Tier
from pipeline import M0Pipeline
from storage.repositories import (
    InMemoryBlockingRepo,
    InMemoryEdgeRepo,
    InMemoryEntityRepo,
    InMemoryEvidenceRepo,
    InMemoryMergeRepo,
    InMemoryObservationRepo,
    InMemoryOpportunityRepo,
    InMemoryReviewRepo,
    InMemorySignalRepo,
    InMemoryTimelineRepo,
    InMemoryTransitionRepo,
)

FEED = (Path(__file__).parent.parent / "fixtures/collectors/rss_blog/acme_feed.xml").read_text()
FEED_URL = "https://acme.com/blog/feed.xml"


def _collect():
    collector = get_collector("rss_blog")
    collector._seeds = [FEED_URL]
    fetch = StubFetchClient({FEED_URL: (200, "application/rss+xml", FEED)})
    ctx = make_context("company_web", fetch, InMemoryRawStore(), trace_id="t")
    return CollectorRuntime(collector, ctx, InMemoryEventBus()).run()


def test_rss_collector_is_registered_without_core_changes():
    assert "rss_blog" in __import__("collectors").REGISTRY


def test_rss_yields_company_posts_authors_signals():
    result = _collect()
    kinds = [(c.kind, c.entity_type or c.signal_type) for c in result.candidates]
    assert ("entity", "company") in kinds
    assert ("entity", "post") in kinds
    assert ("entity", "person") in kinds           # authors
    assert ("signal", "funding_raised") in kinds
    assert ("signal", "pain_mention") in kinds
    assert all(c.evidence and c.evidence.url for c in result.candidates)


def test_rss_pipeline_produces_gold():
    result = _collect()
    repos = dict(
        entities=InMemoryEntityRepo(), evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(), opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(), observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(), merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(), transitions=InMemoryTransitionRepo(),
        edges=InMemoryEdgeRepo(),
    )
    M0Pipeline(**repos).ingest(result.candidates, content_hash="rss-1")
    tiers = {o.tier for o in repos["opportunities"].list()}
    # Funding + CRM pain -> Silver. Authors are resolved as people but "Author"
    # is not a leadership role, so they correctly do NOT trigger Gold.
    assert Tier.SILVER.value in tiers
    assert Tier.GOLD.value not in tiers
    people = repos["entities"].all_of_type("person")
    assert {p.attributes.get("full_name") for p in people} >= {"Jane Roe", "Marcus Lee"}
