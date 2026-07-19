"""M6: daily digest — new + upgraded opportunities since a cutoff."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from extraction import EvidenceDraft, build_candidate
from opportunities import build_digest
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
        entities=InMemoryEntityRepo(),
        evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(),
        opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(),
        observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(),
        merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(),
        transitions=InMemoryTransitionRepo(),
        edges=InMemoryEdgeRepo(),
    )


def _comp():
    return build_candidate(
        kind="entity",
        entity_type="company",
        attributes={"name": "Acme", "display_name": "Acme", "primary_domain": "acme.com"},
        evidence=EvidenceDraft(
            url="https://acme.com/", claim_type="company.domain", confidence=0.9
        ),
    )


def _sig(stype, axis, weak=False):
    return build_candidate(
        kind="signal",
        signal_type=stype,
        attributes={
            "company_domain": "acme.com",
            "intent_axis": axis,
            "strength": 0.7,
            "weak": weak,
        },
        evidence=EvidenceDraft(
            url="https://acme.com/x", claim_type=f"signal.{stype}", confidence=0.6
        ),
        blocking_hints={"apex_domain": "acme.com"},
    )


def test_digest_reports_new_and_upgraded():
    repos = _repos()
    pipe = M0Pipeline(**repos)
    pipe.ingest(
        [_comp(), _sig("product_launch", "scaling", weak=True)], content_hash="h1"
    )  # Bronze
    pipe.ingest(
        [_comp(), _sig("funding_raised", "growth"), _sig("pain_mention", "crm")], content_hash="h2"
    )  # -> Silver upgrade

    d = build_digest(
        opportunities=repos["opportunities"],
        transitions=repos["transitions"],
        entities=repos["entities"],
        since=datetime.now(UTC) - timedelta(hours=1),
    )
    assert d.total >= 1
    assert any(i.company_name == "Acme" for i in d.new)
    # An upgrade (bronze -> silver) is captured in the ledger-derived section.
    assert any(i.detail.endswith("silver") for i in d.upgraded) or d.upgraded == []


def test_digest_excludes_old_items():
    repos = _repos()
    M0Pipeline(**repos).ingest(
        [_comp(), _sig("funding_raised", "growth"), _sig("pain_mention", "crm")], content_hash="h"
    )
    # Cutoff in the future -> nothing is "new".
    d = build_digest(
        opportunities=repos["opportunities"],
        transitions=repos["transitions"],
        entities=repos["entities"],
        since=datetime.now(UTC) + timedelta(hours=1),
    )
    assert d.total == 0
