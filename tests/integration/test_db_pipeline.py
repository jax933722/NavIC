"""M1-B: the full pipeline persisting to real Postgres via the SQL repos.

Proves the DB-backed repositories implement the same protocols the engine and
pipeline expect: a crawled document becomes a persisted Bronze opportunity, a
re-crawl enriches without duplicating, and survivorship + blocking work on the
canonical store. Skips automatically when no database is configured.
"""

from __future__ import annotations

import collectors.sources  # noqa: F401
from collectors import CollectorRuntime
from collectors.registry import get_collector
from collectors.runtime import make_context
from core.eventbus import InMemoryEventBus
from ingestion import InMemoryRawStore, StubFetchClient
from pipeline import M0Pipeline
from storage.sql_repositories import (
    SqlBlockingRepo,
    SqlEntityRepo,
    SqlEvidenceRepo,
    SqlMergeRepo,
    SqlObservationRepo,
    SqlOpportunityRepo,
    SqlReviewRepo,
    SqlSignalRepo,
)

HOMEPAGE = """
<html><head><title>Acme Robotics</title>
<meta property="og:site_name" content="Acme Robotics"/></head>
<body><a href="/careers">Careers</a> we're hiring!</body></html>
"""
URL = "https://www.acme.com/"


def _pipeline(session):
    return M0Pipeline(
        entities=SqlEntityRepo(session),
        evidence=SqlEvidenceRepo(session),
        signals=SqlSignalRepo(session),
        opportunities=SqlOpportunityRepo(session),
        blocking=SqlBlockingRepo(session),
        observations=SqlObservationRepo(session),
        reviews=SqlReviewRepo(session),
        merges=SqlMergeRepo(session),
    )


def _candidates():
    collector = get_collector("company_web")
    collector._seeds = [URL]
    fetch = StubFetchClient({URL: (200, "text/html", HOMEPAGE)})
    ctx = make_context("company_web", fetch, InMemoryRawStore(), trace_id="t")
    return CollectorRuntime(collector, ctx, InMemoryEventBus()).run().candidates


def test_pipeline_persists_bronze_opportunity_to_postgres(db_session):
    pipe = _pipeline(db_session)
    result = pipe.ingest(_candidates(), content_hash="hash-1")
    db_session.commit()

    assert result.companies == 1 and result.signals == 1

    opps = SqlOpportunityRepo(db_session).list(tier="bronze")
    assert len(opps) == 1
    opp = opps[0]
    assert opp.opportunity_score > 0
    assert opp.evidence_ids

    company = SqlEntityRepo(db_session).get(opp.company_entity_id)
    assert company.attributes["primary_domain"] == "acme.com"
    assert company.entity_type == "company"


def test_recrawl_enriches_not_duplicates_in_db(db_session):
    pipe = _pipeline(db_session)
    cands = _candidates()
    pipe.ingest(cands, content_hash="h")
    pipe.ingest(cands, content_hash="h")
    db_session.commit()

    entities = SqlEntityRepo(db_session)
    company = entities.find_by_canonical("company", "acme.com")
    assert company is not None
    assert company.version >= 2  # enriched (survivorship recomputed), not duplicated
    assert len(SqlOpportunityRepo(db_session).list()) == 1


def test_blocking_keys_persisted(db_session):
    pipe = _pipeline(db_session)
    pipe.ingest(_candidates(), content_hash="h")
    db_session.commit()

    from entities.blocking import company_blocking_keys

    keys = company_blocking_keys({"name": "Acme Robotics", "primary_domain": "acme.com"})
    found = SqlBlockingRepo(db_session).candidates(keys)
    assert found, "blocking keys should let us recall the company entity"
