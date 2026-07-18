"""Opportunity engine — M0 assembly + tiering + promotion ledger (spec 05 §3–§5).

M0 ships one template ("hiring_activity"): a company with a domain and a weak
hiring signal yields a Bronze opportunity. The engine regenerates opportunities
on every touch, classifies the tier, records tier transitions, and scores.
Additional templates and the full flywheel arrive in M2.
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

from .tiering import OpportunityPresence, Tier, classify


@dataclass
class Transition:
    company_entity_id: int
    from_tier: str | None
    to_tier: str
    reason: str


@dataclass
class EvaluateResult:
    opportunities: list[OpportunityRow] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)


# Minimal template catalog for M0 (declarative motifs arrive as YAML in M2).
_M0_TEMPLATE = {
    "id": "hiring_activity",
    "thesis": "Active hiring — early buying signal",
    "intent_axis": "hiring",
}


class OpportunityEngine:
    def __init__(
        self,
        entities: EntityRepository,
        signals: SignalRepository,
        opportunities: OpportunityRepository,
    ):
        self._entities = entities
        self._signals = signals
        self._opps = opportunities

    def evaluate(self, company_entity_id: int) -> EvaluateResult:
        result = EvaluateResult()
        company = self._entities.get(company_entity_id)
        if company is None:
            return result
        has_domain = bool(company.attributes.get("primary_domain"))
        company_signals = self._signals.for_company(company_entity_id)
        if not (has_domain and company_signals):
            return result

        template = _M0_TEMPLATE
        weak = any(s.attributes.get("weak") for s in company_signals)
        presence = OpportunityPresence(
            company=True,
            domain=has_domain,
            buying_signal=not weak,
            weak_signal=weak,
        )
        tier = classify(presence)
        if tier is Tier.UNQUALIFIED:
            return result

        score = self._score(tier, company_signals)
        prior = self._opps.find(company_entity_id, template["id"])
        row = OpportunityRow(
            id=0,
            company_entity_id=company_entity_id,
            tier=tier.value,
            template_id=template["id"],
            thesis=template["thesis"],
            opportunity_score=score,
            primary_signal_id=company_signals[0].id,
            evidence_ids=[eid for s in company_signals for eid in s.evidence_ids],
        )
        saved = self._opps.upsert(row)
        result.opportunities.append(saved)

        prior_tier = prior.tier if prior else None
        if prior_tier != saved.tier:
            result.transitions.append(
                Transition(
                    company_entity_id=company_entity_id,
                    from_tier=prior_tier,
                    to_tier=saved.tier,
                    reason=f"template {template['id']} matched; tier={saved.tier}",
                )
            )
        return result

    def _score(self, tier: Tier, signals) -> float:
        now = datetime.now(UTC)
        sig_inputs = [
            SignalInput(
                signal_type=s.signal_type,
                strength=s.strength,
                intent_weight=0.7,
                detected_at=s.detected_at,
            )
            for s in signals
        ]
        bi = buying_intent(sig_inputs, now)
        fr = freshness(sig_inputs, now)
        es = evidence_score([0.5 for s in signals], distinct_source_domains=1)
        return opportunity_score(
            tier=tier, buying_intent_v=bi, evidence_v=es, freshness_v=fr
        )
