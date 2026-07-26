"""M4: person resolution + works_at edge (relationship evidence) -> Gold.

A company with a qualifying signal AND a resolved leadership person connected via
a works_at edge produces a Gold opportunity (person + role + domain + evidence +
signal), the platform's headline output."""

from __future__ import annotations

from extraction import EvidenceDraft, build_candidate
from opportunities import Tier
from pipeline import M0Pipeline
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


def _repos():
    return dict(
        entities=InMemoryEntityRepo(), evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(), opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(), observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(), merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(), transitions=InMemoryTransitionRepo(),
        edges=InMemoryEdgeRepo(),
    )


def _company():
    return build_candidate(
        kind="entity", entity_type="company",
        attributes={"name": "Acme", "display_name": "Acme", "primary_domain": "acme.com"},
        evidence=EvidenceDraft(url="https://acme.com/", claim_type="company.domain",
                               confidence=0.9),
    )


def _person(name, role):
    return build_candidate(
        kind="entity", entity_type="person",
        attributes={"full_name": name, "name": name, "current_role": role,
                    "company_apex": "acme.com", "company_domain": "acme.com"},
        evidence=EvidenceDraft(url="https://acme.com/team", claim_type="person.role",
                               confidence=0.8),
        blocking_hints={"name": name, "company_apex": "acme.com"},
    )


def _sig(stype, axis, strength=0.7):
    return build_candidate(
        kind="signal", signal_type=stype,
        attributes={"company_domain": "acme.com", "intent_axis": axis, "strength": strength},
        evidence=EvidenceDraft(url="https://acme.com/x", claim_type=f"signal.{stype}",
                               confidence=0.6),
        blocking_hints={"apex_domain": "acme.com"},
    )


def test_person_plus_signal_yields_gold():
    repos = _repos()
    pipe = M0Pipeline(**repos)
    result = pipe.ingest(
        [_company(), _person("Jane Roe", "VP of Sales"),
         _sig("funding_raised", "growth"), _sig("pain_mention", "crm")],
        content_hash="h1",
    )
    assert result.people == 1

    gold = [o for o in repos["opportunities"].list() if o.tier == Tier.GOLD.value]
    assert gold, "a leadership person + signal should produce Gold"
    opp = gold[0]
    assert opp.person_entity_id is not None
    assert "sales" in (opp.decision_maker_role or "").lower()
    assert opp.evidence_ids  # includes signal + relationship evidence

    # The works_at edge exists with evidence (the relationship proof).
    person = repos["entities"].get(opp.person_entity_id)
    edges = repos["edges"].out_edges(person.id, "works_at")
    assert edges and edges[0].evidence_ids


def test_no_person_stays_silver():
    repos = _repos()
    pipe = M0Pipeline(**repos)
    pipe.ingest([_company(), _sig("funding_raised", "growth"), _sig("pain_mention", "crm")],
                content_hash="h1")
    tiers = {o.tier for o in repos["opportunities"].list()}
    assert Tier.GOLD.value not in tiers
    assert Tier.SILVER.value in tiers
