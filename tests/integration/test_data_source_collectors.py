"""Greenhouse / News / Funding collectors (spec 03 §7). Golden-fixture driven.

Three structured public-data sources: a job board (Greenhouse), an entity-tagged
news feed, and a funding-round database. Each plugs in via @register with no core
changes and produces evidence-backed companies and signals.
"""

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


def test_data_source_collectors_registered():
    assert {"greenhouse", "news", "funding"} <= set(REGISTRY)


def test_greenhouse_emits_company_hiring_and_expansion():
    body = (FIX / "greenhouse/board.json").read_text()
    result = _run("greenhouse", "https://boards-api.greenhouse.io/v1/boards/stark/jobs", body)

    company = next(c for c in result.candidates if c.entity_type == "company")
    assert company.attributes["primary_domain"] == "starkrobotics.com"

    hiring = [c for c in result.candidates if c.signal_type == "hiring"]
    assert len(hiring) == 5  # one per open role
    depts = {c.attributes.get("department") for c in hiring}
    assert {"Sales", "Engineering", "Marketing"} <= depts
    # An unmapped role (Office Coordinator) still yields a weak hiring signal.
    assert any(c.attributes.get("weak") for c in hiring)

    # >= 5 open roles rolls up into an expansion (scaling) signal.
    expansion = [c for c in result.candidates if c.signal_type == "expansion"]
    assert expansion and expansion[0].attributes["open_roles"] == 5
    assert all(c.evidence and c.evidence.url for c in result.candidates)


def test_news_uses_tagged_subject_company_not_publisher():
    body = (FIX / "news/articles.json").read_text()
    result = _run("news", "https://newsapi.example/v2/everything", body)

    domains = {c.attributes.get("primary_domain") for c in result.candidates
               if c.entity_type == "company"}
    # Companies come from the tagged subject, never the publisher's domain.
    assert {"soylent-corp.com", "tyrell.io"} <= domains
    assert "techpress.example" not in domains
    assert "devnews.example" not in domains

    stypes = {c.signal_type for c in result.candidates if c.kind == "signal"}
    assert "funding_raised" in stypes   # Soylent Series A
    assert "hiring" in stypes           # hiring across sales and engineering
    assert "product_launch" in stypes   # Tyrell launches platform

    # An article with no tagged company is skipped entirely.
    assert len([c for c in result.candidates if c.entity_type == "company"]) == 2


def test_funding_emits_structured_round_signal():
    body = (FIX / "funding/rounds.json").read_text()
    result = _run("funding", "https://fundingdb.example/rounds", body)

    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    assert {"wonka.com", "gekkotech.com"} <= companies

    rounds = {c.attributes.get("round"): c for c in result.candidates
              if c.signal_type == "funding_raised"}
    assert rounds["Series B"].attributes["amount_usd"] == 45000000.0
    assert rounds["Series B"].attributes["strength"] == 0.8
    assert "Sequoia" in rounds["Series B"].attributes["investors"]
    # Amount given as a numeric string is coerced to a float.
    assert rounds["Seed"].attributes["amount_usd"] == 2000000.0

    # A round with no resolvable company domain is skipped.
    assert "No Domain Co" not in {c.attributes.get("name") for c in result.candidates}
    assert all(c.evidence and c.evidence.url for c in result.candidates)
