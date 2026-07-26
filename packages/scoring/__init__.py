"""scoring — the multi-score vector and composite opportunity score (spec 05 §6).

Multiple independent, explainable scores. Never one opaque number (invariant O3).
"""

from .functions import (
    DEFAULT_TAU_DAYS,
    SignalInput,
    buying_intent,
    evidence_score,
    freshness,
    opportunity_score,
    tier_multiplier,
)

__all__ = [
    "SignalInput",
    "buying_intent",
    "evidence_score",
    "freshness",
    "opportunity_score",
    "tier_multiplier",
    "DEFAULT_TAU_DAYS",
]
