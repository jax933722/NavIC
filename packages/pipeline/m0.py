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
from graph import GraphBuilder
from opportunities import EvaluateResult, OpportunityEngine
from storage.repositories import (
    EntityRepository,
    EvidenceRepository,
    InMemoryBlockingRepo,
    InMemoryEdgeRepo,
    InMemoryMergeRepo,
    InMemoryObservationRepo,
    InMemoryReviewRepo,
    InMemoryTimelineRepo,
    InMemoryTransitionRepo,
    OpportunityRepository,
    SignalRepository,
)

log = get_logger("pipeline.m0")


@dataclass
class PipelineResult:
    companies: int = 0
    people: int = 0
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
        timeline: InMemoryTimelineRepo | None = None,
        transitions: InMemoryTransitionRepo | None = None,
        edges: InMemoryEdgeRepo | None = None,
    ):
        self._entities = entities
        self._evidence = evidence
        self._signals = signals
        self._opps = opportunities
        self._timeline = timeline or InMemoryTimelineRepo()
        self._transitions = transitions or InMemoryTransitionRepo()
        self._edges = edges or InMemoryEdgeRepo()
        self._graph = GraphBuilder(self._edges)
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
        self._engine = OpportunityEngine(entities, signals, opportunities, edges=self._edges)

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

        # Pass 1b: resolve people and connect them to their company (works_at edge
        # with relationship evidence — the requirement that unlocks Gold).
        for cand in candidates:
            if not (cand.kind == "entity" and cand.entity_type == "person"):
                continue
            apex = cand.attributes.get("company_apex") or cand.attributes.get("company_domain")
            company_id = apex_to_entity.get(apex) if apex else None
            if company_id is None and apex:
                found = self._entities.find_by_canonical("company", apex)
                company_id = found.id if found else None
            res = self._resolver.resolve_person(cand, content_hash or cand.evidence.url)
            if company_id is not None:
                self._graph.works_at(
                    person_id=res.entity_id, company_id=company_id,
                    role=cand.attributes.get("current_role"),
                    evidence_ids=[res.evidence_id],
                )
                touched.add(company_id)
            result.people += 1

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
            sig = self._signals.add(
                company_entity_id=entity_id,
                signal_type=cand.signal_type or "other",
                strength=float(cand.attributes.get("strength", 0.4)),
                intent_axis=cand.attributes.get("intent_axis"),
                evidence_ids=[ev.id],
                attributes=cand.attributes,
            )
            # Append to the company's timeline (spec 05 §2).
            self._timeline.add(
                company_entity_id=entity_id,
                event_type=cand.signal_type or "signal",
                summary=cand.evidence.snippet,
                signal_id=sig.id,
                evidence_ids=[ev.id],
            )
            result.signals += 1
            touched.add(entity_id)

        # Pass 3: (re)generate opportunities for every touched company; persist transitions.
        for entity_id in touched:
            evaluated: EvaluateResult = self._engine.evaluate(entity_id)
            result.opportunities.extend(evaluated.opportunities)
            for t in evaluated.transitions:
                self._transitions.add(
                    opportunity_id=t.opportunity_id, from_tier=t.from_tier,
                    to_tier=t.to_tier, reason=t.reason, score_delta=t.score_delta,
                )
            result.transitions.extend(evaluated.transitions)
        return result
