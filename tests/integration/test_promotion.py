"""M2: multi-template engine, Silver inference, timeline, and promotion ledger.

Drives the pipeline with a doc rich enough to satisfy a template and shows the
company promote to Silver with an inferred decision-maker, a recorded transition,
and timeline events — all over in-memory repos."""

from __future__ import annotations

from extraction import EvidenceDraft, build_candidate
from opportunities import Tier
from pipeline import M0Pipeline
from storage.repositories import (
    InMemoryBlockingRepo,
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


def _repos():
    return dict(
        entities=InMemoryEntityRepo(), evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(), opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(), observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(), merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(), transitions=InMemoryTransitionRepo(),
    )


def _company(domain="acme.com"):
    return build_candidate(
        kind="entity", entity_type="company",
        attributes={"name": "Acme", "display_name": "Acme", "primary_domain": domain},
        evidence=EvidenceDraft(url=f"https://{domain}/", claim_type="company.domain",
                               confidence=0.9),
    )


def _signal(stype, axis, domain="acme.com", weak=False, strength=0.7):
    return build_candidate(
        kind="signal", signal_type=stype,
        attributes={"company_domain": domain, "intent_axis": axis, "strength": strength,
                    "weak": weak},
        evidence=EvidenceDraft(url=f"https://{domain}/x", claim_type=f"signal.{stype}",
                               confidence=0.6),
        blocking_hints={"apex_domain": domain},
    )


def test_bronze_then_silver_promotion_with_transition():
    repos = _repos()
    pipe = M0Pipeline(**repos)

    # First crawl: only a weak launch signal -> Bronze early_signal.
    pipe.ingest([_company(), _signal("product_launch", "scaling", weak=True, strength=0.5)],
                content_hash="h1")
    opps = repos["opportunities"].list()
    assert len(opps) == 1 and opps[0].tier == Tier.BRONZE.value

    # Second crawl adds funding + pain(crm) -> crm_in_market satisfied -> Silver.
    pipe.ingest([_company(),
                 _signal("funding_raised", "growth"),
                 _signal("pain_mention", "crm")],
                content_hash="h2")

    silver = [o for o in repos["opportunities"].list() if o.tier == Tier.SILVER.value]
    assert silver, "crm_in_market should promote the company to Silver"
    opp = silver[0]
    assert opp.department == "Sales"
    assert opp.decision_maker_role  # inferred decision maker present (Silver requirement)

    # A transition into silver was recorded.
    trans = repos["transitions"].for_opportunity(opp.id)
    assert any(t.to_tier == "silver" for t in trans)


def test_timeline_events_recorded():
    repos = _repos()
    pipe = M0Pipeline(**repos)
    pipe.ingest([_company(),
                 _signal("funding_raised", "growth"),
                 _signal("pain_mention", "crm")],
                content_hash="h1")
    company = repos["entities"].find_by_canonical("company", "acme.com")
    events = repos["timeline"].for_company(company.id)
    kinds = {e.event_type for e in events}
    assert "funding_raised" in kinds and "pain_mention" in kinds
