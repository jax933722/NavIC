"""M5 search over the pipeline output (in-memory)."""

from __future__ import annotations

from extraction import EvidenceDraft, build_candidate
from pipeline import M0Pipeline
from search import SearchService
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


def _setup():
    repos = dict(
        entities=InMemoryEntityRepo(), evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(), opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(), observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(), merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(), transitions=InMemoryTransitionRepo(),
        edges=InMemoryEdgeRepo(),
    )
    pipe = M0Pipeline(**repos)

    def comp(name, domain):
        return build_candidate(kind="entity", entity_type="company",
            attributes={"name": name, "display_name": name, "primary_domain": domain},
            evidence=EvidenceDraft(url=f"https://{domain}/", claim_type="company.domain",
                                   confidence=0.9))

    def sig(domain, stype, axis, dept=None, tech=None):
        attrs = {"company_domain": domain, "intent_axis": axis, "strength": 0.7}
        if dept:
            attrs["department"] = dept
        if tech:
            attrs["tech"] = tech
        return build_candidate(kind="signal", signal_type=stype, attributes=attrs,
            evidence=EvidenceDraft(url=f"https://{domain}/x", claim_type=f"signal.{stype}",
                                   snippet=f"{stype} {axis}", confidence=0.6),
            blocking_hints={"apex_domain": domain})

    pipe.ingest([comp("Acme", "acme.com"),
                 sig("acme.com", "hiring", "hiring", dept="Sales"),
                 sig("acme.com", "tech_adoption", "hubspot", tech="hubspot"),
                 sig("acme.com", "pain_mention", "crm")], content_hash="h1")
    pipe.ingest([comp("Globex", "globex.com"),
                 sig("globex.com", "hiring", "hiring", dept="Engineering")], content_hash="h2")

    svc = SearchService(entities=repos["entities"], signals=repos["signals"],
                        opportunities=repos["opportunities"], edges=repos["edges"],
                        evidence=repos["evidence"])
    return svc


def test_companies_hiring_sdr():
    svc = _setup()
    _, results = svc.search("companies hiring SDR")
    names = {r.name for r in results}
    assert "Acme" in names and "Globex" not in names  # Globex hires Engineering, not Sales


def test_companies_using_hubspot():
    svc = _setup()
    _, results = svc.search("companies using HubSpot")
    assert any(r.name == "Acme" for r in results)
    assert all("tech:hubspot" in r.matched_on for r in results)


def test_companies_looking_for_crm():
    svc = _setup()
    intent, results = svc.search("companies looking for CRM")
    assert intent.looking_for_axis == "crm"
    assert any(r.name == "Acme" for r in results)
    assert results[0].evidence_ids  # evidence attached


def test_no_match_returns_empty():
    svc = _setup()
    _, results = svc.search("companies using Salesforce")
    assert results == []
