"""M3: GitHub + Hacker News collectors (API-first, JSON). Golden-fixture driven."""

from __future__ import annotations

from pathlib import Path

import collectors.sources  # noqa: F401
from collectors import REGISTRY, CollectorRuntime
from collectors.registry import get_collector
from collectors.runtime import make_context
from core.eventbus import InMemoryEventBus
from ingestion import InMemoryRawStore, StubFetchClient

FIX = Path(__file__).parent.parent / "fixtures/collectors"


def _run(slug, url, body, content_type="application/json"):
    collector = get_collector(slug)
    collector._seeds = [url]
    fetch = StubFetchClient({url: (200, content_type, body)})
    ctx = make_context(collector.source_slug, fetch, InMemoryRawStore(), trace_id="t")
    return CollectorRuntime(collector, ctx, InMemoryEventBus()).run()


def test_collectors_registered():
    assert {"github_org", "hackernews"} <= set(REGISTRY)


def test_github_org_yields_company_tech_people():
    body = (FIX / "github/acme_org.json").read_text()
    result = _run("github_org", "https://api.github.com/orgs/acme", body)
    kinds = [(c.kind, c.entity_type or c.signal_type) for c in result.candidates]
    assert ("entity", "company") in kinds
    assert ("signal", "tech_adoption") in kinds
    assert ("entity", "person") in kinds
    techs = {c.attributes.get("tech") for c in result.candidates
             if c.signal_type == "tech_adoption"}
    assert "snowflake" in techs
    # A CTO member is present (leadership -> can drive Gold downstream).
    roles = {c.attributes.get("current_role") for c in result.candidates
             if c.entity_type == "person"}
    assert "CTO" in roles
    assert all(c.evidence and c.evidence.url for c in result.candidates)


def test_hackernews_yields_companies_and_signals():
    body = (FIX / "hackernews/stories.json").read_text()
    result = _run("hackernews", "https://hn.example/top.json", body)
    domains = {c.attributes.get("primary_domain") for c in result.candidates
               if c.entity_type == "company"}
    assert {"globex.com", "initech.com"} <= domains
    stypes = {c.signal_type for c in result.candidates if c.kind == "signal"}
    assert "funding_raised" in stypes and "pain_mention" in stypes
    # HN authors are NOT emitted as company employees (no false works_at).
    assert not any(c.entity_type == "person" for c in result.candidates)
