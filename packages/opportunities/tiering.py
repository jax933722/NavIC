"""Gold / Silver / Bronze classification (spec 05 §4).

Deterministic gate over presence-of-fields, exactly per the master spec. Ranking
*within* a tier is the scoring engine's job (spec 05 §6); this only assigns the band.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Tier(StrEnum):
    GOLD = "gold"
    SILVER = "silver"
    BRONZE = "bronze"
    UNQUALIFIED = "unqualified"


@dataclass(frozen=True)
class OpportunityPresence:
    """Which qualifying fields are present for a candidate opportunity."""

    company: bool = False
    domain: bool = False
    buying_signal: bool = False        # a qualifying (non-weak) signal
    weak_signal: bool = False          # weak/early signal (Bronze floor)
    person: bool = False
    role: bool = False
    relationship_evidence: bool = False  # person<->company works_at backed by evidence
    suggested_department: bool = False
    suggested_role: bool = False


def classify(p: OpportunityPresence) -> Tier:
    """Return the maturity tier for the given presence set."""
    if (
        p.person
        and p.company
        and p.domain
        and p.role
        and p.relationship_evidence
        and p.buying_signal
    ):
        return Tier.GOLD
    if (
        p.company
        and p.domain
        and p.buying_signal
        and p.suggested_department
        and p.suggested_role
    ):
        return Tier.SILVER
    if p.company and p.domain and (p.weak_signal or p.buying_signal):
        return Tier.BRONZE
    return Tier.UNQUALIFIED
