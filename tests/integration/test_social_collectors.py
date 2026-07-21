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


def test_hn_freelance_auto_monitor_yields_buyer_requests():
    # Automated inbound: HN "Seeking Freelancer" buyer comments -> solicitation leads.
    body = (FIX / "hn_freelance/search.json").read_text()
    result = _run("hn_freelance", "https://hn.algolia.com/api/v1/search_by_date", body)

    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    assert {"northwindlabs.io", "brightbrew.co"} <= companies

    sols = [c for c in result.candidates if c.signal_type == "solicitation"]
    axes = {c.attributes.get("intent_axis") for c in sols}
    assert "web_development" in axes  # Northwind: React/Node
    # Budget/stack are lifted from the request text.
    nw = next(c for c in sols if c.attributes["company_domain"] == "northwindlabs.io")
    assert nw.attributes.get("budget") == "$8000"
    assert "react" in (nw.attributes.get("stack") or [])

    # "SEEKING WORK" (a freelancer offering) is NOT ingested as a buyer.
    assert "janedev.example" not in companies
    # An anonymous buyer with no company link is skipped (can't anchor it).
    assert all(c.attributes.get("primary_domain") for c in result.candidates
               if c.entity_type == "company")


def test_reddit_forhire_monitor_ingests_only_buyers():
    body = (FIX / "reddit_forhire/listing.json").read_text()
    result = _run("reddit_forhire", "https://www.reddit.com/r/forhire/new.json", body)

    companies = {c.attributes.get("primary_domain") for c in result.candidates
                 if c.entity_type == "company"}
    # [Hiring] posts that name a company (bare or URL) -> leads.
    assert {"gearloftgear.com", "cogwheel-labs.io"} <= companies
    # [For Hire] (a freelancer advertising) is a seller -> never ingested.
    assert "devportfolio.example" not in companies

    sols = [c for c in result.candidates if c.signal_type == "solicitation"]
    gear = next(c for c in sols if c.attributes["company_domain"] == "gearloftgear.com")
    assert gear.attributes["intent_axis"] == "web_design"  # Shopify product pages
    assert gear.attributes.get("budget") == "$2500"

    # A buyer post with no company link is skipped (nothing to anchor).
    assert all(c.attributes.get("primary_domain") for c in result.candidates
               if c.entity_type == "company")


def test_reddit_search_surfaces_requirement_posts():
    # "People posted what they need" — kept only when it's an actual service request.
    body = (FIX / "reddit_search/search.json").read_text()
    result = _run("reddit_search", "https://www.reddit.com/search.json?q=x", body)

    sols = [c for c in result.candidates if c.signal_type == "solicitation"]
    axes = {c.attributes.get("intent_axis") for c in sols}
    assert "web_development" in axes  # "looking for a web developer ... Shopify"
    assert "security" in axes         # "recommend a WordPress malware removal expert"

    companies = {c.attributes.get("name") for c in result.candidates
                 if c.entity_type == "company"}
    # A post that links a company anchors on its domain...
    assert "gearloft.co" in companies
    # ...an individual's request with no company link anchors on the poster.
    assert "u/shop_owner" in companies
    # An off-topic "looking for a good book" post is NOT a service request -> dropped.
    assert not any("book" in (c.evidence.snippet or "").lower() for c in result.candidates)
    # Budget lifted from the request text.
    shop = next(c for c in sols if c.attributes["company_domain"] == "shop-owner")
    assert shop.attributes.get("budget") == "$1500"


def test_reddit_forhire_is_buyer_covers_employer_subs():
    from collectors.sources.reddit_forhire import _is_buyer

    assert _is_buyer({"title": "[Hiring] Need a dev", "subreddit": "forhire"}) is True
    assert _is_buyer({"title": "[For Hire] Available dev", "subreddit": "forhire"}) is False
    # Employer-listing subs have no "[Hiring]" tag but are buyer-side by default.
    assert _is_buyer({"title": "Senior Go Engineer", "subreddit": "jobbit"}) is True
    # ...unless the poster explicitly marks it For Hire.
    assert _is_buyer({"title": "[For Hire] Go dev", "subreddit": "jobbit"}) is False
    # A random sub with no hiring marker is not assumed to be a buyer.
    assert _is_buyer({"title": "Cool project", "subreddit": "programming"}) is False


def test_default_feeds_are_broadened():
    from collectors.sources.reddit_forhire import RedditForHireCollector
    from collectors.sources.weworkremotely import WeWorkRemotelyCollector

    # Fresh instances carry the broadened out-of-the-box seed lists.
    reddit_subs = RedditForHireCollector()._seeds
    assert len(reddit_subs) >= 5 and any("jobbit" in u for u in reddit_subs)
    wwr = WeWorkRemotelyCollector()._seeds
    assert len(wwr) >= 5 and any("categories/remote-programming" in u for u in wwr)


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
