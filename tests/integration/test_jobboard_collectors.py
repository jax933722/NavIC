"""Lever / Ashby / Workable job-board collectors (spec 03 §7).

All three share packages/collectors/jobboard.py: each normalizes its provider's JSON
into {title, department, location, url} jobs and emits the company + one hiring signal
per open role (+ an expansion signal at >= 5 roles). Golden-fixture driven.
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


def _run(slug, url, body):
    collector = get_collector(slug)
    collector._seeds = [url]
    fetch = StubFetchClient({url: (200, "application/json", body)})
    ctx = make_context(collector.source_slug, fetch, InMemoryRawStore(), trace_id="t")
    return CollectorRuntime(collector, ctx, InMemoryEventBus()).run()


def test_jobboard_collectors_registered():
    assert {"lever", "ashby", "workable"} <= set(REGISTRY)


def _company_and_depts(result):
    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    depts = {c.attributes.get("department") for c in result.candidates
             if c.signal_type == "hiring"}
    return companies, depts


def test_lever_emits_company_and_hiring():
    result = _run("lever", "https://api.lever.co/v0/postings/cyberdyne",
                  (FIX / "lever/postings.json").read_text())
    companies, depts = _company_and_depts(result)
    assert "cyberdyne.com" in companies
    assert {"Sales", "Engineering", "Marketing"} <= depts  # Growth -> Marketing (title-inferred)
    assert all(c.evidence and c.evidence.url for c in result.candidates)


def test_ashby_emits_company_and_hiring():
    result = _run("ashby", "https://api.ashbyhq.com/posting-api/job-board/weyland",
                  (FIX / "ashby/board.json").read_text())
    companies, depts = _company_and_depts(result)
    assert "weyland.io" in companies
    assert {"Sales", "Engineering", "Data"} <= depts  # team fallback + Data Analyst title


def test_workable_emits_company_hiring_and_flattens_location():
    result = _run("workable", "https://tyrell.workable.com/spi/v3/jobs",
                  (FIX / "workable/jobs.json").read_text())
    companies, depts = _company_and_depts(result)
    assert "tyrell.com" in companies
    assert {"Sales", "Engineering"} <= depts
    sdr = next(c for c in result.candidates
               if c.signal_type == "hiring" and c.attributes.get("role") == "Sales Development Rep")
    assert sdr.attributes["location"] == "Austin, TX, United States"  # dict flattened
    # Office Manager has no mappable department -> weak hiring signal.
    assert any(c.attributes.get("weak") for c in result.candidates if c.signal_type == "hiring")
