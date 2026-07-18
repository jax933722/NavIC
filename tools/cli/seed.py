"""Seed CLI — run the company_web collector + M0 pipeline over URLs.

    python -m tools.cli.seed https://example.com https://acme.com

Fetches each URL, persists raw to .data/raw, extracts an evidence-backed company
+ hiring signal, and prints the resulting opportunities. Uses in-memory repos
(self-contained run); the DB-backed path lands with the storage adapters.
"""

from __future__ import annotations

import argparse
import sys

from ingestion import HttpFetchClient, LocalFileRawStore
from pipeline import M0Pipeline, ingest_company_web_urls
from storage.repositories import (
    InMemoryEntityRepo,
    InMemoryEvidenceRepo,
    InMemoryOpportunityRepo,
    InMemorySignalRepo,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed NavIC from company homepage URLs.")
    parser.add_argument("urls", nargs="+", help="one or more homepage URLs")
    args = parser.parse_args(argv)

    entities = InMemoryEntityRepo()
    evidence = InMemoryEvidenceRepo()
    signals = InMemorySignalRepo()
    opportunities = InMemoryOpportunityRepo()
    pipeline = M0Pipeline(
        entities=entities, evidence=evidence, signals=signals, opportunities=opportunities
    )

    summary = ingest_company_web_urls(
        args.urls,
        pipeline=pipeline,
        fetch=HttpFetchClient(),
        raw_store=LocalFileRawStore(),
    )

    print(
        f"fetched={summary.fetched} companies={summary.companies} "
        f"signals={summary.signals} opportunities={summary.opportunities}"
    )
    for opp in opportunities.list():
        company = entities.get(opp.company_entity_id)
        domain = company.attributes.get("primary_domain") if company else "?"
        print(f"  [{opp.tier.upper():6}] {domain:30} score={opp.opportunity_score:.3f}  {opp.thesis}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
