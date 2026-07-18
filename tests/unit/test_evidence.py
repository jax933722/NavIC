import pytest

from core.errors import EvidenceRequired
from extraction import EvidenceDraft, build_candidate


def _evidence():
    return EvidenceDraft(
        url="https://acme.com/team",
        claim_type="person.role",
        snippet="Jane Roe — VP Sales",
        confidence=0.8,
    )


def test_candidate_requires_evidence():
    with pytest.raises(EvidenceRequired):
        build_candidate(kind="entity", entity_type="person", evidence=None)


def test_candidate_with_evidence_ok():
    c = build_candidate(
        kind="entity",
        entity_type="person",
        attributes={"full_name": "Jane Roe"},
        evidence=_evidence(),
        blocking_hints={"apex_domain": "acme.com"},
    )
    assert c.kind == "entity"
    assert c.evidence.claim_type == "person.role"
    assert c.blocking_hints["apex_domain"] == "acme.com"


def test_evidence_rejects_empty_url():
    with pytest.raises(ValueError):
        EvidenceDraft(url="   ", claim_type="person.role")


def test_evidence_confidence_bounds():
    with pytest.raises(ValueError):
        EvidenceDraft(url="https://x", claim_type="c", confidence=1.5)


def test_invalid_kind():
    with pytest.raises(ValueError):
        build_candidate(kind="widget", evidence=_evidence())
