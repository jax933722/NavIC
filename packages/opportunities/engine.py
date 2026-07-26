"""Opportunity engine — multi-template assembly, tiering, promotion (spec 05 §3-§5).

For each company touched by a signal, the engine regenerates opportunities from
the declarative templates, classifies each Gold/Silver/Bronze, records tier
transitions, and scores. A satisfied template with a qualifying signal yields a
Silver opportunity (person unknown) with an inferred department + decision-maker
role; companies with only weak/early signal get a Bronze "early_signal". Gold is
produced in M4 when a person in the right role is resolved with relationship
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from scoring import (
    SignalInput,
    buying_intent,
    evidence_score,
    freshness,
    opportunity_score,
)
from storage.repositories import (
    EntityRepository,
    OpportunityRepository,
    OpportunityRow,
    SignalRepository,
)

from .taxonomy_bridge import decision_maker_for
from .templates_loader import Template, load_templates
from .tiering import OpportunityPresence, Tier, classify

_BRONZE_TEMPLATE_ID = "early_signal"


@dataclass
class Transition:
    company_entity_id: int
    opportunity_id: int
    from_tier: str | None
    to_tier: str
    reason: str
    score_delta: float


@dataclass
class EvaluateResult:
    opportunities: list[OpportunityRow] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)


class OpportunityEngine:
    def __init__(
        self,
        entities: EntityRepository,
        signals: SignalRepository,
        opportunities: OpportunityRepository,
        edges=None,
    ):
        self._entities = entities
        self._signals = signals
        self._opps = opportunities
        self._edges = edges

    def evaluate(self, company_entity_id: int) -> EvaluateResult:
        result = EvaluateResult()
        company = self._entities.get(company_entity_id)
        if company is None or not company.attributes.get("primary_domain"):
            return result
        company_signals = self._signals.for_company(company_entity_id)
        if not company_signals:
            return result

        matched_any = False
        for template in load_templates():
            matching = _matching_signals(template, company_signals)
            if _satisfies(template, matching):
                matched_any = True
                self._emit(result, company_entity_id, template, matching, tier=Tier.SILVER)

        if not matched_any:
            # No template satisfied, but signals exist -> Bronze early signal.
            self._emit_bronze(result, company_entity_id, company_signals)
        return result

    def _emit(self, result, company_id, template: Template, matching, tier: Tier) -> None:
        department = _best_department(matching, template.suggested_department)
        dm_role = decision_maker_for(department, template.suggested_decision_maker_role)

        # Gold: a resolved leadership person connected to this company via a
        # works_at edge (relationship evidence) upgrades the opportunity.
        person = self._find_decision_maker(company_id, department)
        if person is not None:
            person_id, person_role, rel_evidence = person
            presence = OpportunityPresence(
                company=True, domain=True, buying_signal=True, person=True, role=True,
                relationship_evidence=True,
            )
            final_tier = classify(presence)
            evidence_ids = [e for s in matching for e in s.evidence_ids] + rel_evidence
            row = OpportunityRow(
                id=0, company_entity_id=company_id, tier=final_tier.value,
                template_id=template.id, thesis=template.thesis,
                opportunity_score=self._score(final_tier, matching),
                department=department, decision_maker_role=person_role,
                person_entity_id=person_id, primary_signal_id=matching[0].id,
                evidence_ids=evidence_ids,
            )
            self._save(result, company_id, row, self._opps.find(company_id, template.id))
            return

        presence = OpportunityPresence(
            company=True, domain=True, buying_signal=True,
            suggested_department=bool(department), suggested_role=bool(dm_role),
        )
        final_tier = classify(presence)
        score = self._score(final_tier, matching)
        prior = self._opps.find(company_id, template.id)
        row = OpportunityRow(
            id=0, company_entity_id=company_id, tier=final_tier.value, template_id=template.id,
            thesis=template.thesis, opportunity_score=score,
            department=department, decision_maker_role=dm_role,
            primary_signal_id=matching[0].id,
            evidence_ids=[e for s in matching for e in s.evidence_ids],
        )
        self._save(result, company_id, row, prior)

    def _find_decision_maker(self, company_id: int, department: str):
        """Return (person_id, role, evidence_ids) for a leadership person at the
        company via a works_at edge, preferring a department match. Gold requires
        this relationship evidence (spec 05 §4)."""
        if self._edges is None:
            return None
        candidates = []
        for edge in self._edges.in_edges(company_id, "works_at"):
            if not edge.evidence_ids:
                continue
            role = (edge.attributes or {}).get("role")
            if not edge.attributes.get("leadership"):
                continue
            dept_match = bool(department) and department.lower() in (role or "").lower()
            candidates.append((dept_match, edge.src_entity_id, role, list(edge.evidence_ids)))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0], reverse=True)  # prefer department match
        _, person_id, role, evidence_ids = candidates[0]
        return person_id, role, evidence_ids

    def _emit_bronze(self, result, company_id, signals) -> None:
        presence = OpportunityPresence(company=True, domain=True, weak_signal=True)
        tier = classify(presence)
        score = self._score(tier, signals)
        prior = self._opps.find(company_id, _BRONZE_TEMPLATE_ID)
        row = OpportunityRow(
            id=0, company_entity_id=company_id, tier=tier.value, template_id=_BRONZE_TEMPLATE_ID,
            thesis="Early buying signal", opportunity_score=score,
            primary_signal_id=signals[0].id,
            evidence_ids=[e for s in signals for e in s.evidence_ids],
        )
        self._save(result, company_id, row, prior)

    def _save(self, result, company_id, row, prior) -> None:
        saved = self._opps.upsert(row)
        result.opportunities.append(saved)
        prior_tier = prior.tier if prior else None
        if prior_tier != saved.tier:
            prior_score = prior.opportunity_score if prior else 0.0
            result.transitions.append(
                Transition(
                    company_entity_id=company_id, opportunity_id=saved.id,
                    from_tier=prior_tier, to_tier=saved.tier,
                    reason=f"template {saved.template_id} -> {saved.tier}",
                    score_delta=round(saved.opportunity_score - prior_score, 4),
                )
            )

    def _score(self, tier: Tier, signals) -> float:
        now = datetime.now(UTC)
        sig_inputs = [
            SignalInput(signal_type=s.signal_type, strength=s.strength,
                        intent_weight=0.7, detected_at=s.detected_at)
            for s in signals
        ]
        bi = buying_intent(sig_inputs, now)
        fr = freshness(sig_inputs, now)
        es = evidence_score([0.6] * len(signals), distinct_source_domains=1)
        return opportunity_score(tier=tier, buying_intent_v=bi, evidence_v=es, freshness_v=fr)


def _matching_signals(template: Template, signals) -> list:
    """Signals whose type is one the template requires."""
    if not template.requires_any_signals:
        return list(signals)
    return [s for s in signals if s.signal_type in template.requires_any_signals]


def _satisfies(template: Template, matching: list) -> bool:
    if len(matching) < template.min_signals:
        return False
    if not any(not s.attributes.get("weak") for s in matching):
        return False  # need at least one qualifying (non-weak) signal
    # Gate: at least one type-matched signal must touch a required intent axis.
    if template.require_intent_axis:
        return any(s.intent_axis in template.require_intent_axis for s in matching)
    return True


def _best_department(signals, fallback: str) -> str:
    for s in signals:
        dept = s.attributes.get("department")
        if dept:
            return dept
    return fallback
