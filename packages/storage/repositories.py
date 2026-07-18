"""Repository interfaces + in-memory implementations (spec 01 §2, blueprint §7.3).

Modules talk to repositories, never to each other's tables. The in-memory repo
backs unit/integration tests and local runs; the SQLAlchemy repo (added when the
DB stack is wired) implements the same protocols. Single-writer discipline is a
convention enforced by which module holds which repo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count
from typing import Protocol


# ------------------------------------------------------------------ DTOs (storage-neutral)
@dataclass
class EvidenceRow:
    id: int
    url: str
    claim_type: str
    snippet: str | None
    confidence: float
    content_hash: str
    observed_at: datetime


@dataclass
class EntityRow:
    id: int
    entity_type: str
    canonical_key: str | None
    display_name: str | None
    attributes: dict = field(default_factory=dict)
    version: int = 1
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class SignalRow:
    id: int
    company_entity_id: int
    signal_type: str
    strength: float
    intent_axis: str | None
    evidence_ids: list[int]
    detected_at: datetime
    attributes: dict = field(default_factory=dict)


@dataclass
class OpportunityRow:
    id: int
    company_entity_id: int
    tier: str
    template_id: str | None
    thesis: str | None
    opportunity_score: float
    department: str | None = None
    decision_maker_role: str | None = None
    person_entity_id: int | None = None
    primary_signal_id: int | None = None
    status: str = "open"
    evidence_ids: list[int] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ------------------------------------------------------------------ protocols
class EvidenceRepository(Protocol):
    def add(self, *, url: str, claim_type: str, snippet: str | None, confidence: float,
            content_hash: str) -> EvidenceRow: ...
    def get(self, evidence_id: int) -> EvidenceRow | None: ...


class EntityRepository(Protocol):
    def find_by_canonical(self, entity_type: str, canonical_key: str) -> EntityRow | None: ...
    def upsert_canonical(self, entity_type: str, canonical_key: str, display_name: str | None,
                         attributes: dict) -> EntityRow: ...
    def get(self, entity_id: int) -> EntityRow | None: ...


class SignalRepository(Protocol):
    def add(self, *, company_entity_id: int, signal_type: str, strength: float,
            intent_axis: str | None, evidence_ids: list[int], attributes: dict) -> SignalRow: ...
    def for_company(self, company_entity_id: int) -> list[SignalRow]: ...


class OpportunityRepository(Protocol):
    def upsert(self, row: OpportunityRow) -> OpportunityRow: ...
    def find(self, company_entity_id: int, template_id: str | None) -> OpportunityRow | None: ...
    def list(self, tier: str | None = None) -> list[OpportunityRow]: ...
    def get(self, opportunity_id: int) -> OpportunityRow | None: ...


# ------------------------------------------------------------------ in-memory implementations
class InMemoryEvidenceRepo:
    def __init__(self) -> None:
        self._rows: dict[int, EvidenceRow] = {}
        self._ids = count(1)

    def add(self, *, url, claim_type, snippet, confidence, content_hash) -> EvidenceRow:
        row = EvidenceRow(
            id=next(self._ids), url=url, claim_type=claim_type, snippet=snippet,
            confidence=confidence, content_hash=content_hash, observed_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    def get(self, evidence_id: int) -> EvidenceRow | None:
        return self._rows.get(evidence_id)


class InMemoryEntityRepo:
    def __init__(self) -> None:
        self._rows: dict[int, EntityRow] = {}
        self._by_key: dict[tuple[str, str], int] = {}
        self._ids = count(1)

    def find_by_canonical(self, entity_type, canonical_key) -> EntityRow | None:
        eid = self._by_key.get((entity_type, canonical_key))
        return self._rows.get(eid) if eid else None

    def upsert_canonical(self, entity_type, canonical_key, display_name, attributes) -> EntityRow:
        existing = self.find_by_canonical(entity_type, canonical_key)
        if existing:
            # Enrich, never replace: merge attributes, bump version (spec 01 I1/I4).
            existing.attributes = {**existing.attributes, **attributes}
            existing.display_name = existing.display_name or display_name
            existing.last_seen_at = datetime.now(UTC)
            existing.version += 1
            return existing
        row = EntityRow(
            id=next(self._ids), entity_type=entity_type, canonical_key=canonical_key,
            display_name=display_name, attributes=attributes,
        )
        self._rows[row.id] = row
        self._by_key[(entity_type, canonical_key)] = row.id
        return row

    def get(self, entity_id: int) -> EntityRow | None:
        return self._rows.get(entity_id)

    # -- engine-oriented API (M1 resolution engine) --
    def create_blank(self, entity_type: str) -> EntityRow:
        row = EntityRow(
            id=next(self._ids), entity_type=entity_type, canonical_key=None,
            display_name=None, attributes={},
        )
        self._rows[row.id] = row
        return row

    def set_projection(
        self, entity_id: int, canonical_key: str | None, display_name: str | None, attributes: dict
    ) -> EntityRow:
        row = self._rows[entity_id]
        if canonical_key and row.canonical_key != canonical_key:
            self._by_key[(row.entity_type, canonical_key)] = entity_id
            row.canonical_key = canonical_key
        row.display_name = display_name or row.display_name
        row.attributes = attributes
        row.last_seen_at = datetime.now(UTC)
        row.version += 1
        return row

    def repoint(self, from_entity_id: int, to_entity_id: int) -> None:
        """Re-point a merged entity's canonical keys to the survivor."""
        row = self._rows.get(from_entity_id)
        if row:
            row.attributes = {**row.attributes, "merged_into": to_entity_id}
            for key, eid in list(self._by_key.items()):
                if eid == from_entity_id:
                    self._by_key[key] = to_entity_id


class InMemorySignalRepo:
    def __init__(self) -> None:
        self._rows: dict[int, SignalRow] = {}
        self._by_key: dict[tuple[int, str, str | None], int] = {}
        self._ids = count(1)

    def add(self, *, company_entity_id, signal_type, strength, intent_axis, evidence_ids,
            attributes) -> SignalRow:
        # Idempotent per (company, type, axis): a re-crawl refreshes, never
        # duplicates. Distinct axes remain distinct signals.
        key = (company_entity_id, signal_type, intent_axis)
        existing_id = self._by_key.get(key)
        if existing_id:
            row = self._rows[existing_id]
            row.strength = max(row.strength, strength)
            row.evidence_ids = sorted(set(row.evidence_ids) | set(evidence_ids))
            row.detected_at = datetime.now(UTC)
            row.attributes = attributes
            return row
        row = SignalRow(
            id=next(self._ids), company_entity_id=company_entity_id, signal_type=signal_type,
            strength=strength, intent_axis=intent_axis, evidence_ids=list(evidence_ids),
            attributes=attributes, detected_at=datetime.now(UTC),
        )
        self._rows[row.id] = row
        self._by_key[key] = row.id
        return row

    def for_company(self, company_entity_id: int) -> list[SignalRow]:
        return [r for r in self._rows.values() if r.company_entity_id == company_entity_id]


class InMemoryOpportunityRepo:
    def __init__(self) -> None:
        self._rows: dict[int, OpportunityRow] = {}
        self._by_key: dict[tuple[int, str | None], int] = {}
        self._ids = count(1)

    def upsert(self, row: OpportunityRow) -> OpportunityRow:
        existing = self.find(row.company_entity_id, row.template_id)
        if existing:
            row.id = existing.id
            row.created_at = existing.created_at
            row.updated_at = datetime.now(UTC)
        else:
            row.id = next(self._ids)
        self._rows[row.id] = row
        self._by_key[(row.company_entity_id, row.template_id)] = row.id
        return row

    def find(self, company_entity_id, template_id) -> OpportunityRow | None:
        oid = self._by_key.get((company_entity_id, template_id))
        return self._rows.get(oid) if oid else None

    def list(self, tier: str | None = None) -> list[OpportunityRow]:
        rows = list(self._rows.values())
        if tier and tier != "all":
            rows = [r for r in rows if r.tier == tier]
        return sorted(rows, key=lambda r: r.opportunity_score, reverse=True)

    def get(self, opportunity_id: int) -> OpportunityRow | None:
        return self._rows.get(opportunity_id)


@dataclass
class TransitionRow:
    id: int
    opportunity_id: int
    from_tier: str | None
    to_tier: str
    reason: str | None
    score_delta: float | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class TimelineEventRow:
    id: int
    company_entity_id: int
    event_type: str
    summary: str | None
    signal_id: int | None
    evidence_ids: list[int]
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryTransitionRepo:
    def __init__(self) -> None:
        self._rows: dict[int, TransitionRow] = {}
        self._ids = count(1)

    def add(self, opportunity_id, from_tier, to_tier, reason, score_delta) -> TransitionRow:
        row = TransitionRow(id=next(self._ids), opportunity_id=opportunity_id,
                            from_tier=from_tier, to_tier=to_tier, reason=reason,
                            score_delta=score_delta)
        self._rows[row.id] = row
        return row

    def for_opportunity(self, opportunity_id: int) -> list[TransitionRow]:
        return sorted(
            (r for r in self._rows.values() if r.opportunity_id == opportunity_id),
            key=lambda r: r.created_at,
        )


class InMemoryTimelineRepo:
    def __init__(self) -> None:
        self._rows: dict[int, TimelineEventRow] = {}
        self._ids = count(1)

    def add(self, *, company_entity_id, event_type, summary, signal_id, evidence_ids,
            occurred_at=None) -> TimelineEventRow:
        row = TimelineEventRow(
            id=next(self._ids), company_entity_id=company_entity_id, event_type=event_type,
            summary=summary, signal_id=signal_id, evidence_ids=list(evidence_ids),
            occurred_at=occurred_at or datetime.now(UTC),
        )
        self._rows[row.id] = row
        return row

    def for_company(self, company_entity_id: int) -> list[TimelineEventRow]:
        return sorted(
            (r for r in self._rows.values() if r.company_entity_id == company_entity_id),
            key=lambda r: r.occurred_at,
        )


# ------------------------------------------------------------------ ER repositories (M1)
@dataclass
class ObservationRow:
    id: int
    entity_id: int
    source_slug: str
    source_trust_tier: str
    external_id: str | None
    raw_attributes: dict
    evidence_id: int
    match_prob: float | None
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ReviewRow:
    id: int
    left_entity: int
    right_entity: int
    match_prob: float
    features: dict
    decision: str | None = None


@dataclass
class MergeRow:
    id: int
    surviving_entity_id: int
    merged_entity_id: int
    method: str
    confidence: float
    features: dict


class InMemoryBlockingRepo:
    """entity_id <-> blocking-key index (spec 04 §4)."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], set[int]] = {}
        self._by_entity: dict[int, set[tuple[str, str]]] = {}

    def add(self, entity_id: int, key_type: str, key_value: str) -> None:
        k = (key_type, key_value)
        self._by_key.setdefault(k, set()).add(entity_id)
        self._by_entity.setdefault(entity_id, set()).add(k)

    def candidates(self, keys) -> set[int]:
        out: set[int] = set()
        for k in keys:
            out |= self._by_key.get((k.key_type, k.key_value), set())
        return out

    def block_size(self, key_type: str, key_value: str) -> int:
        return len(self._by_key.get((key_type, key_value), set()))


class InMemoryObservationRepo:
    def __init__(self) -> None:
        self._rows: dict[int, ObservationRow] = {}
        self._ids = count(1)

    def add(self, **kw) -> ObservationRow:
        row = ObservationRow(id=next(self._ids), **kw)
        self._rows[row.id] = row
        return row

    def for_entity(self, entity_id: int) -> list[ObservationRow]:
        return [r for r in self._rows.values() if r.entity_id == entity_id]

    def repoint(self, from_entity_id: int, to_entity_id: int) -> None:
        for r in self._rows.values():
            if r.entity_id == from_entity_id:
                r.entity_id = to_entity_id


class InMemoryReviewRepo:
    def __init__(self) -> None:
        self._rows: dict[int, ReviewRow] = {}
        self._ids = count(1)

    def add(
        self, left_entity: int, right_entity: int, match_prob: float, features: dict
    ) -> ReviewRow:
        row = ReviewRow(id=next(self._ids), left_entity=left_entity, right_entity=right_entity,
                        match_prob=match_prob, features=features)
        self._rows[row.id] = row
        return row

    def pending(self) -> list[ReviewRow]:
        return [r for r in self._rows.values() if r.decision is None]

    def get(self, review_id: int) -> ReviewRow | None:
        return self._rows.get(review_id)


class InMemoryMergeRepo:
    def __init__(self) -> None:
        self._rows: dict[int, MergeRow] = {}
        self._ids = count(1)

    def add(self, **kw) -> MergeRow:
        row = MergeRow(id=next(self._ids), **kw)
        self._rows[row.id] = row
        return row

    def all(self) -> list[MergeRow]:
        return list(self._rows.values())
