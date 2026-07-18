"""Entity resolution — M0 domain-exact resolver (spec 04 §5.4).

Company observations sharing an apex domain resolve to the same canonical entity
(the hard rule that requires no fuzzy scoring). Every observation persists its
evidence first (invariant I2) and enriches the canonical projection, never
replacing it (I1/I4). Blocking + probabilistic matching arrive in M1.
"""

from __future__ import annotations

from dataclasses import dataclass

from extraction import CandidateRecord
from storage.repositories import EntityRepository, EntityRow, EvidenceRepository


@dataclass
class ResolutionResult:
    entity: EntityRow
    evidence_id: int
    action: str  # 'created' | 'attached'


class DomainExactResolver:
    def __init__(self, entities: EntityRepository, evidence: EvidenceRepository):
        self._entities = entities
        self._evidence = evidence

    def resolve_company(self, cand: CandidateRecord, content_hash: str) -> ResolutionResult:
        if cand.entity_type != "company":
            raise ValueError("resolve_company expects a company candidate")
        apex = cand.attributes.get("primary_domain") or cand.attributes.get("canonical_key")
        if not apex:
            raise ValueError("company candidate has no domain to resolve on")

        ev = self._evidence.add(
            url=cand.evidence.url,
            claim_type=cand.evidence.claim_type,
            snippet=cand.evidence.snippet,
            confidence=cand.evidence.confidence,
            content_hash=content_hash,
        )
        existing = self._entities.find_by_canonical("company", apex)
        entity = self._entities.upsert_canonical(
            entity_type="company",
            canonical_key=apex,
            display_name=cand.attributes.get("display_name") or cand.attributes.get("name"),
            attributes={
                "primary_domain": apex,
                "name": cand.attributes.get("name"),
                # Track which evidence supports the domain claim (survivorship seed).
                "domain_evidence_ids": [ev.id],
            },
        )
        return ResolutionResult(
            entity=entity, evidence_id=ev.id, action="attached" if existing else "created"
        )
