"""Survivorship (spec 04 §8).

The canonical value of each attribute is chosen from all observations by
evidence weight -> source trust -> recency -> multiplicity. Never last-write.
The result is deterministic, so the canonical projection is fully recomputable
from observations (invariant I4). Each field records its chosen evidence and the
losing alternatives, so conflicts stay visible and reversible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Source trust tiers (spec 04 §I2 / source.trust_tier).
SOURCE_TRUST: dict[str, float] = {
    "official": 1.0,
    "verified_api": 0.85,
    "news": 0.6,
    "community": 0.4,
    "inferred": 0.2,
}

_VOLATILE_FIELDS = frozenset({"current_role", "funding_stage", "employee_range", "seniority"})
_FRESHNESS_TAU_DAYS = 365.0


@dataclass
class Observation:
    field_values: dict          # {attribute: value}
    source_trust_tier: str
    evidence_id: int
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _freshness(observed_at: datetime, now: datetime) -> float:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    age_days = max(0.0, (now - observed_at).total_seconds() / 86400.0)
    return 2.718281828 ** (-age_days / _FRESHNESS_TAU_DAYS)


def project(observations: list[Observation], now: datetime | None = None) -> dict:
    """Return the canonical attribute projection with provenance per field."""
    now = now or datetime.now(UTC)
    # Gather per (field, value) candidates.
    fields: dict[str, dict] = {}
    for obs in observations:
        trust = SOURCE_TRUST.get(obs.source_trust_tier, 0.3)
        fresh = _freshness(obs.observed_at, now)
        for fname, value in obs.field_values.items():
            if value is None or value == "":
                continue
            bucket = fields.setdefault(fname, {})
            key = _hashable(value)
            entry = bucket.setdefault(
                key,
                {"value": value, "weight": 0.0, "trust": 0.0, "count": 0,
                 "latest": obs.observed_at, "evidence_ids": []},
            )
            entry["weight"] += trust * fresh
            entry["trust"] = max(entry["trust"], trust)
            entry["count"] += 1
            entry["evidence_ids"].append(obs.evidence_id)
            if obs.observed_at > entry["latest"]:
                entry["latest"] = obs.observed_at

    projection: dict = {}
    for fname, candidates in fields.items():
        ranked = sorted(
            candidates.values(),
            key=lambda e: _rank_key(fname, e),
            reverse=True,
        )
        winner = ranked[0]
        projection[fname] = winner["value"]
        projection[f"{fname}__provenance"] = {
            "chosen_value": winner["value"],
            "chosen_evidence_ids": sorted(set(winner["evidence_ids"])),
            "weight": round(winner["weight"], 4),
            "alternatives": [
                {"value": e["value"], "weight": round(e["weight"], 4),
                 "evidence_ids": sorted(set(e["evidence_ids"]))}
                for e in ranked[1:]
            ],
        }
    return projection


def _rank_key(fname: str, entry: dict):
    # weight -> trust -> (recency for volatile fields) -> multiplicity
    recency = entry["latest"].timestamp() if fname in _VOLATILE_FIELDS else 0.0
    return (round(entry["weight"], 6), round(entry["trust"], 6), recency, entry["count"])


def _hashable(value):
    if isinstance(value, (list, dict)):
        return str(value)
    return value
