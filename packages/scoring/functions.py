"""Score functions (spec 05 §6.1).

Each score is a documented, explainable function of stored features (invariant O3,
FR-SCORE-2). Weights/tau are runtime config in production (``scoring_config``);
defaults here mirror spec 05 §8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from opportunities.tiering import Tier

# Decay time-constants in days, per signal type (spec 05 §6.1 / §8).
DEFAULT_TAU_DAYS: dict[str, float] = {
    "funding_raised": 180.0,
    "hiring": 90.0,
    "pain_mention": 30.0,
    "product_launch": 120.0,
    "tech_adoption": 120.0,
    "tech_churn": 120.0,
    "leadership_change": 120.0,
    "default": 90.0,
}

_TIER_MULTIPLIER: dict[Tier, float] = {
    Tier.GOLD: 1.0,
    Tier.SILVER: 0.7,
    Tier.BRONZE: 0.4,
    Tier.UNQUALIFIED: 0.0,
}

# Opportunity-score weights (spec 05 §8 os_weights).
DEFAULT_OS_WEIGHTS: dict[str, float] = {
    "bi": 0.28,
    "es": 0.14,
    "fr": 0.16,
    "rs": 0.12,
    "ts": 0.10,
    "cc": 0.12,
    "ic": 0.08,
}


@dataclass(frozen=True)
class SignalInput:
    """The features of one signal needed for scoring."""

    signal_type: str
    strength: float                 # [0,1] raw classifier strength
    intent_weight: float            # weight for this intent axis/type
    detected_at: datetime


def _age_days(then: datetime, now: datetime) -> float:
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0.0, (now - then).total_seconds() / 86400.0)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def signal_freshness(sig: SignalInput, now: datetime, tau: dict[str, float] | None = None) -> float:
    tau = tau or DEFAULT_TAU_DAYS
    t = tau.get(sig.signal_type, tau["default"])
    return math.exp(-_age_days(sig.detected_at, now) / t)


def freshness(
    signals: list[SignalInput], now: datetime | None = None, tau: dict[str, float] | None = None
) -> float:
    """FR = recency of the most recent driving signal (spec 05 §6.1 #5)."""
    if not signals:
        return 0.0
    now = now or datetime.now(UTC)
    return max(signal_freshness(s, now, tau) for s in signals)


def buying_intent(
    signals: list[SignalInput], now: datetime | None = None, tau: dict[str, float] | None = None
) -> float:
    """BI = noisy-OR over intent signals; independent signals compound, each decays.

    BI = 1 - Π(1 - strength_i * intent_weight_i * freshness_i)   (spec 05 §6.1 #3)
    """
    if not signals:
        return 0.0
    now = now or datetime.now(UTC)
    product = 1.0
    for s in signals:
        contrib = _clamp(s.strength) * _clamp(s.intent_weight) * signal_freshness(s, now, tau)
        product *= 1.0 - _clamp(contrib)
    return _clamp(1.0 - product)


def evidence_score(source_trust_freshness: list[float], distinct_source_domains: int) -> float:
    """ES = tanh(Σ trust_i*freshness_i) * (1 + diversity_bonus) (spec 05 §6.1 #4)."""
    base = math.tanh(sum(max(0.0, x) for x in source_trust_freshness))
    diversity_bonus = 0.1 * math.log1p(max(0, distinct_source_domains - 1))
    return _clamp(base * (1.0 + diversity_bonus))


def tier_multiplier(tier: Tier) -> float:
    return _TIER_MULTIPLIER[tier]


def opportunity_score(
    *,
    tier: Tier,
    buying_intent_v: float,
    evidence_v: float,
    freshness_v: float,
    relationship_v: float = 0.0,
    timeline_v: float = 0.0,
    company_confidence_v: float = 0.0,
    identity_confidence_v: float = 0.0,
    weights: dict[str, float] | None = None,
) -> float:
    """OS = (Σ w_i * score_i) * tier_multiplier(tier)  (spec 05 §6.1 #8).

    A strong Bronze can out-rank a weak Silver on raw signal, but the tier
    multiplier anchors the band (invariant O3).
    """
    w = weights or DEFAULT_OS_WEIGHTS
    combined = (
        w["bi"] * _clamp(buying_intent_v)
        + w["es"] * _clamp(evidence_v)
        + w["fr"] * _clamp(freshness_v)
        + w["rs"] * _clamp(relationship_v)
        + w["ts"] * _clamp(timeline_v)
        + w["cc"] * _clamp(company_confidence_v)
        + w["ic"] * _clamp(identity_confidence_v)
    )
    return _clamp(combined * tier_multiplier(tier))
