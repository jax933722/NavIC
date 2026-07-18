"""Resolution engine (spec 04 §2).

Ties the ER pipeline together for companies (and people):
  normalize -> block -> score pairs -> decide -> attach/create -> survivorship.

Decisions (spec 04 §6): p>=0.90 auto-attach; 0.60<=p<0.90 create-new + queue a
review (biases to under-merge, the safe error, P2); p<0.60 create-new. Every
attach records an entity_merge audit; survivorship recomputes the canonical
projection from all observations after each change.
"""

from __future__ import annotations

from dataclasses import dataclass

from extraction import CandidateRecord

from .blocking import company_blocking_keys, person_blocking_keys
from .matcher import score_company_pair, score_person_pair
from .survivorship import SOURCE_TRUST, Observation, project

AUTO_MERGE = 0.90
REVIEW_LOW = 0.60
_BLOCK_SIZE_GUARD = 50  # require a co-key beyond huge blocks


@dataclass
class ResolutionResult:
    entity_id: int
    evidence_id: int
    action: str          # 'created' | 'attached' | 'review'
    match_prob: float
    review_id: int | None = None


class ResolutionEngine:
    def __init__(
        self,
        *,
        entities,
        evidence,
        observations,
        blocking,
        reviews,
        merges,
        auto_merge: float = AUTO_MERGE,
        review_low: float = REVIEW_LOW,
    ):
        self._entities = entities
        self._evidence = evidence
        self._obs = observations
        self._blocking = blocking
        self._reviews = reviews
        self._merges = merges
        self.auto_merge = auto_merge
        self.review_low = review_low

    # ------------------------------------------------------------------ company
    def resolve_company(self, cand: CandidateRecord, content_hash: str,
                        source_trust: str = "official") -> ResolutionResult:
        return self._resolve(
            cand, content_hash, source_trust,
            entity_type="company",
            blocking_keys=company_blocking_keys,
            scorer=score_company_pair,
            canonical_key_of=lambda attrs: attrs.get("primary_domain"),
        )

    # ------------------------------------------------------------------ person
    def resolve_person(self, cand: CandidateRecord, content_hash: str,
                       source_trust: str = "community") -> ResolutionResult:
        return self._resolve(
            cand, content_hash, source_trust,
            entity_type="person",
            blocking_keys=person_blocking_keys,
            scorer=score_person_pair,
            canonical_key_of=lambda attrs: (
                attrs.get("github_handle") or attrs.get("email")
            ),
        )

    # ------------------------------------------------------------------ core
    def _resolve(self, cand, content_hash, source_trust, *, entity_type,
                 blocking_keys, scorer, canonical_key_of) -> ResolutionResult:
        attrs = dict(cand.attributes)
        ev = self._evidence.add(
            url=cand.evidence.url, claim_type=cand.evidence.claim_type,
            snippet=cand.evidence.snippet, confidence=cand.evidence.confidence,
            content_hash=content_hash or cand.evidence.url,
        )

        keys = blocking_keys(attrs)
        candidate_ids = self._blocking.candidates(keys)

        best_id, best_prob, best_features = None, 0.0, {}
        for cid in candidate_ids:
            existing = self._entities.get(cid)
            if existing is None or existing.attributes.get("merged_into"):
                continue
            prob = scorer(attrs, existing.attributes)
            if prob > best_prob:
                best_id, best_prob, best_features = cid, prob, {"match_prob": prob}

        if best_id is not None and best_prob >= self.auto_merge:
            entity = self._entities.get(best_id)
            action, review_id = "attached", None
            if best_prob < 1.0:  # not a hard-rule attach -> log the merge decision
                self._merges.add(
                    surviving_entity_id=best_id, merged_entity_id=best_id,
                    method="rules:v1", confidence=best_prob, features=best_features,
                )
        else:
            entity = self._entities.create_blank(entity_type)
            action = "created"
            review_id = None
            if best_id is not None and best_prob >= self.review_low:
                # Under-merge is the safe error: keep separate, queue a review.
                r = self._reviews.add(best_id, entity.id, best_prob, best_features)
                review_id = r.id
                action = "review"

        # Record the observation, refresh blocking, recompute survivorship.
        self._obs.add(
            entity_id=entity.id, source_slug=source_trust, source_trust_tier=source_trust,
            external_id=attrs.get("external_id"), raw_attributes=attrs,
            evidence_id=ev.id, match_prob=best_prob,
        )
        for k in blocking_keys(attrs):
            self._blocking.add(entity.id, k.key_type, k.key_value)
        self._reproject(entity.id, canonical_key_of)

        return ResolutionResult(
            entity_id=entity.id, evidence_id=ev.id, action=action,
            match_prob=best_prob, review_id=review_id,
        )

    def _reproject(self, entity_id: int, canonical_key_of) -> None:
        obs_rows = self._obs.for_entity(entity_id)
        observations = [
            Observation(
                field_values=r.raw_attributes,
                source_trust_tier=(
                    r.source_trust_tier if r.source_trust_tier in SOURCE_TRUST else "community"
                ),
                evidence_id=r.evidence_id,
                observed_at=r.observed_at,
            )
            for r in obs_rows
        ]
        projection = project(observations)
        canonical_key = canonical_key_of(projection)
        display = (
            projection.get("display_name")
            or projection.get("name")
            or projection.get("full_name")
        )
        self._entities.set_projection(entity_id, canonical_key, display, projection)

    # ------------------------------------------------------------------ review + un-merge
    def decide_review(self, review_id: int, decision: str, canonical_key_of=None) -> None:
        review = self._reviews.get(review_id)
        if review is None:
            return
        review.decision = decision
        if decision == "merge":
            self.merge(review.right_entity, review.left_entity)

    def merge(self, from_entity_id: int, into_entity_id: int) -> None:
        """Merge ``from`` into ``into``: repoint observations, recompute, audit."""
        if from_entity_id == into_entity_id:
            return
        self._obs.repoint(from_entity_id, into_entity_id)
        self._entities.repoint(from_entity_id, into_entity_id)
        self._merges.add(
            surviving_entity_id=into_entity_id, merged_entity_id=from_entity_id,
            method="manual", confidence=1.0, features={},
        )
        survivor = self._entities.get(into_entity_id)
        key_of = (lambda a: a.get("primary_domain")) if survivor.entity_type == "company" \
            else (lambda a: a.get("github_handle") or a.get("email"))
        self._reproject(into_entity_id, key_of)
