"""Reddit / Product Hunt / LinkedIn collectors (spec 03 §7). Golden-fixture driven.

These prove the pluggable-source contract for public social/community sources.
Reddit and Product Hunt use only public data; the LinkedIn collector ingests
AUTHORIZED data (official API / export) and never scrapes the auth-walled site.
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


def test_social_collectors_registered():
    assert {"reddit", "producthunt", "linkedin"} <= set(REGISTRY)


def test_reddit_links_companies_and_signals_not_authors():
    body = (FIX / "reddit/listing.json").read_text()
    result = _run("reddit", "https://www.reddit.com/r/startups/.json", body)

    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    assert {"globex.com", "initech.com"} <= companies
    # self-hosted (text-only) reddit posts do not create a reddit.com company
    assert "reddit.com" not in companies

    stypes = {c.signal_type for c in result.candidates if c.kind == "signal"}
    assert "funding_raised" in stypes  # Globex Series B
    assert "hiring" in stypes          # hiring SDRs / AEs
    assert "tech_churn" in stypes      # migrating off Salesforce

    # Redditors are never emitted as company employees (no false works_at).
    assert not any(c.entity_type == "person" for c in result.candidates)
    assert all(c.evidence and c.evidence.url for c in result.candidates)


def test_producthunt_yields_launch_company_and_makers():
    body = (FIX / "producthunt/posts.json").read_text()
    result = _run("producthunt", "https://api.producthunt.com/v2/posts", body)

    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    assert {"umbrella-analytics.com", "nakatomi.io"} <= companies

    launches = [c for c in result.candidates if c.signal_type == "product_launch"]
    assert launches and all(c.attributes.get("intent_axis") == "scaling" for c in launches)

    makers = {c.attributes.get("full_name") for c in result.candidates
              if c.entity_type == "person"}
    assert {"Dana Reyes", "Sam Okafor", "Holly Gennaro"} <= makers
    # Every maker is affiliated with a company apex (drives works_at downstream).
    assert all(c.attributes.get("company_apex") for c in result.candidates
               if c.entity_type == "person")
    # A post with no website is skipped entirely.
    assert "producthunt.com" not in companies


def test_linkedin_authorized_company_people_and_hiring():
    body = (FIX / "linkedin/company.json").read_text()
    result = _run("linkedin", "https://api.linkedin.com/v2/organizations/wayne", body)

    company = next(c for c in result.candidates if c.entity_type == "company")
    assert company.attributes["primary_domain"] == "wayne-analytics.com"
    assert company.attributes["linkedin_slug"] == "wayne-analytics"

    people = {c.attributes.get("full_name") for c in result.candidates
              if c.entity_type == "person"}
    assert {"Lucius Fox", "Barbara Gordon"} <= people
    # A person record with no name is skipped.
    assert None not in people and len(people) == 2

    hiring = [c for c in result.candidates if c.signal_type == "hiring"]
    depts = {c.attributes.get("department") for c in hiring}
    assert "Sales" in depts             # Senior Account Executive -> Sales
    # Unmapped title still yields a (weak) hiring signal.
    assert any(c.attributes.get("weak") for c in hiring)
    assert all(c.evidence and c.evidence.url for c in result.candidates)


def test_linkedin_post_solicitation_becomes_signal():
    # An employee's public "who can I hire?" post is an explicit buying signal
    # attributed to their company (author = in-market buyer).
    body = (FIX / "linkedin/social_post.json").read_text()
    result = _run("linkedin", "https://api.linkedin.com/v2/organizations/pacini", body)

    sol = [c for c in result.candidates if c.signal_type == "solicitation"]
    assert sol, "the Shopify designer request should be detected as a solicitation"
    assert sol[0].attributes["intent_axis"] == "web_design"
    assert sol[0].attributes["company_domain"] == "pacinicommerce.com"

    # The author is emitted as a person at the company (drives the decision-maker).
    people = {c.attributes.get("full_name") for c in result.candidates
              if c.entity_type == "person"}
    assert "Erika Pacini" in people
