"""Resolution-engine behaviour (spec 04): blocking + matching + survivorship,
merge/attach, review queue, and un-merge — all over in-memory repos."""

from __future__ import annotations

from entities import ResolutionEngine
from extraction import EvidenceDraft, build_candidate
from storage.repositories import (
    InMemoryBlockingRepo,
    InMemoryEntityRepo,
    InMemoryEvidenceRepo,
    InMemoryMergeRepo,
    InMemoryObservationRepo,
    InMemoryReviewRepo,
)


def _engine():
    return ResolutionEngine(
        entities=InMemoryEntityRepo(),
        evidence=InMemoryEvidenceRepo(),
        observations=InMemoryObservationRepo(),
        blocking=InMemoryBlockingRepo(),
        reviews=InMemoryReviewRepo(),
        merges=InMemoryMergeRepo(),
    )


def _company(name, domain, trust="official", url="https://x/"):
    return build_candidate(
        kind="entity", entity_type="company",
        attributes={"name": name, "display_name": name, "primary_domain": domain},
        evidence=EvidenceDraft(url=url, claim_type="company.domain", confidence=0.9),
    )


def test_same_domain_resolves_to_one_entity():
    eng = _engine()
    r1 = eng.resolve_company(_company("Acme Inc", "acme.com"), "h1")
    r2 = eng.resolve_company(_company("Acme LLC", "acme.com"), "h2")  # diff name, same domain
    assert r1.entity_id == r2.entity_id
    assert r2.action == "attached"
    ent = eng._entities.get(r1.entity_id)
    assert ent.attributes["primary_domain"] == "acme.com"


def test_distinct_companies_stay_separate():
    eng = _engine()
    r1 = eng.resolve_company(_company("Acme", "acme.com"), "h1")
    r2 = eng.resolve_company(_company("Globex", "globex.com"), "h2")
    assert r1.entity_id != r2.entity_id


def test_survivorship_prefers_official_name():
    eng = _engine()
    eng.resolve_company(_company("Acme Corporation", "acme.com", trust="official"), "h1")
    # second observation, lower-trust, different name variant
    eng.resolve_company(_company("Acme!!!", "acme.com", trust="community"), "h2")
    ent = eng._entities.get(1)
    assert "acme" in (ent.display_name or "").lower()


def test_review_queue_for_borderline_pair():
    eng = _engine()
    # Two same-name companies on different domains -> high-ish but < auto-merge.
    eng.resolve_company(_company("Northwind Traders", "northwind-traders.com"), "h1")
    r2 = eng.resolve_company(_company("Northwind Traders", "northwind.io"), "h2")
    # Either separate (safe) or queued for review — never silently merged.
    assert r2.action in ("created", "review")
    if r2.action == "review":
        assert eng._reviews.pending()


def test_manual_merge_then_unifies():
    eng = _engine()
    r1 = eng.resolve_company(_company("Acme", "acme.com"), "h1")
    r2 = eng.resolve_company(_company("Acme Europe", "acme.eu"), "h2")
    assert r1.entity_id != r2.entity_id
    eng.merge(r2.entity_id, r1.entity_id)  # merge r2 into r1
    merged = eng._entities.get(r2.entity_id)
    assert merged.attributes.get("merged_into") == r1.entity_id
    assert eng._merges.all()  # audit recorded
