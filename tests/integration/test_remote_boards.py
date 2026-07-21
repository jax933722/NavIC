"""RemoteOK + We Work Remotely collectors (spec 03 §7) — broad remote-hiring feeds.

Both anchor on a real company domain parsed from the job's links (skipping the
aggregator + ATS hosts); roles with no anchorable company domain are skipped.
Golden-fixture driven.
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


def test_remote_boards_registered():
    assert {"remoteok", "weworkremotely"} <= set(REGISTRY)


def test_remoteok_anchors_on_company_domain_from_apply_url():
    result = _run("remoteok", "https://remoteok.com/api",
                  (FIX / "remoteok/api.json").read_text())
    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    assert {"globex.io", "initech.com"} <= companies
    # The legal-notice element is not a job; a role whose only link is an ATS host
    # (greenhouse) can't be anchored to the company -> skipped.
    assert "boards.greenhouse.io" not in companies and "greenhouse.io" not in companies
    assert "remoteok.com" not in companies

    hiring = {c.attributes.get("department") for c in result.candidates
              if c.signal_type == "hiring"}
    assert {"Engineering", "Marketing"} <= hiring  # React Developer, Growth Marketer


def test_weworkremotely_parses_company_role_and_domain():
    result = _run("weworkremotely", "https://weworkremotely.com/remote-jobs.rss",
                  (FIX / "weworkremotely/feed.xml").read_text(), content_type="application/rss+xml")
    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    assert {"cloudflare.com", "acmestudio.co"} <= companies
    # No company link in the third item -> skipped; WWR host never anchors.
    assert "weworkremotely.com" not in companies
    names = {c.attributes.get("name") for c in result.candidates if c.entity_type == "company"}
    assert "Cloudflare" in names  # "Company: Role" split
    assert all(c.evidence and c.evidence.url for c in result.candidates)
