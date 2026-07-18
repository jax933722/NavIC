"""M0 pipeline: candidates -> canonical entities + signals -> opportunities.

Takes the candidates a collector produced and drives them through the spine:
  1. company entity candidates -> DomainExactResolver -> canonical company
  2. signal candidates -> attached to their company (by apex) -> signal + evidence
  3. touched companies -> OpportunityEngine -> Bronze opportunity + transition
Idempotent: re-running the same candidates converges (enrich, never replace).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.logging import get_logger
from entities import ResolutionEngine
from extraction import CandidateRecord
from opportunities import EvaluateResult, OpportunityEngine
from storage.repositories import (
    EntityRepository,
    EvidenceRepository,
    InMemoryBlockingRepo,
    InMemoryMergeRepo,
    InMemoryObservationRepo,
    InMemoryReviewRepo,
    OpportunityRepository,
    SignalRepository,
)

log = get_logger("pipeline.m0")


@dataclass
class PipelineResult:
    companies: int = 0
    signals: int = 0
    opportunities: list = field(default_factory=list)
    transitions: list = field(default_factory=list)


class M0Pipeline:
    def __init__(
        self,
        *,
        entities: EntityRepository,
        evidence: EvidenceRepository,
        signals: SignalRepository,
        opportunities: OpportunityRepository,
        blocking: InMemoryBlockingRepo | None = None,
        observations: InMemoryObservationRepo | None = None,
        reviews: InMemoryReviewRepo | None = None,
        merges: InMemoryMergeRepo | None = None,
    ):
        self._entities = entities
        self._evidence = evidence
        self._signals = signals
        self._opps = opportunities
        # ER state must persist across ingests to dedupe, so callers that reuse
        # a pipeline (the API) pass shared repos; standalone runs get fresh ones.
        self._resolver = ResolutionEngine(
            entities=entities,
            evidence=evidence,
            observations=observations or InMemoryObservationRepo(),
            blocking=blocking or InMemoryBlockingRepo(),
            reviews=reviews or InMemoryReviewRepo(),
            merges=merges or InMemoryMergeRepo(),
        )
        self._engine = OpportunityEngine(entities, signals, opportunities)

    def ingest(self, candidates: list[CandidateRecord], content_hash: str = "") -> PipelineResult:
        result = PipelineResult()
        touched: set[int] = set()

        # Pass 1: resolve company entities so signals can attach by apex.
        apex_to_entity: dict[str, int] = {}
        for cand in candidates:
            if cand.kind == "entity" and cand.entity_type == "company":
                res = self._resolver.resolve_company(cand, content_hash or cand.evidence.url)
                apex = cand.attributes.get("primary_domain")
                if apex:
                    apex_to_entity[apex] = res.entity_id
                result.companies += 1
                touched.add(res.entity_id)

        # Pass 2: attach signals to their company.
        for cand in candidates:
            if cand.kind != "signal":
                continue
            apex = cand.attributes.get("company_domain") or cand.blocking_hints.get("apex_domain")
            entity_id = apex_to_entity.get(apex) if apex else None
            if entity_id is None and apex:
                found = self._entities.find_by_canonical("company", apex)
                entity_id = found.id if found else None
            if entity_id is None:
                log.info("orphan signal (no company)", extra={"context": {"apex": apex}})
                continue
            ev = self._evidence.add(
                url=cand.evidence.url,
                claim_type=cand.evidence.claim_type,
                snippet=cand.evidence.snippet,
                confidence=cand.evidence.confidence,
                content_hash=content_hash or cand.evidence.url,
            )
            self._signals.add(
                company_entity_id=entity_id,
                signal_type=cand.signal_type or "other",
                strength=float(cand.attributes.get("strength", 0.4)),
                intent_axis=cand.attributes.get("intent_axis"),
                evidence_ids=[ev.id],
                attributes=cand.attributes,
            )
            result.signals += 1
            touched.add(entity_id)

        # Pass 3: (re)generate opportunities for every touched company.
        for entity_id in touched:
            evaluated: EvaluateResult = self._engine.evaluate(entity_id)
            result.opportunities.extend(evaluated.opportunities)
            result.transitions.extend(evaluated.transitions)
        return result
