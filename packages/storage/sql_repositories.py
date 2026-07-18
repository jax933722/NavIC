"""SQLAlchemy repository implementations (spec 01).

These implement the same protocols as the in-memory repos and return the same
storage-neutral DTOs, so the engine/pipeline/API are unchanged when swapping to
Postgres. Each repo is bound to a Session; use one set per unit of work.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .repositories import (
    EntityRow,
    EvidenceRow,
    MergeRow,
    ObservationRow,
    OpportunityRow,
    ReviewRow,
    SignalRow,
)


def _hash_bytes(h: str) -> bytes:
    return h.encode("utf-8") if isinstance(h, str) else h


class SqlEvidenceRepo:
    def __init__(self, session: Session):
        self.s = session

    def add(self, *, url, claim_type, snippet, confidence, content_hash) -> EvidenceRow:
        row = m.Evidence(
            source_id=0, collector_id=0, url=url, content_hash=_hash_bytes(content_hash),
            claim_type=claim_type, snippet=snippet, confidence=confidence,
        )
        self.s.add(row)
        self.s.flush()
        return EvidenceRow(row.id, row.url, row.claim_type, row.snippet, row.confidence,
                           content_hash, row.observed_at)

    def get(self, evidence_id: int) -> EvidenceRow | None:
        row = self.s.get(m.Evidence, evidence_id)
        if row is None:
            return None
        return EvidenceRow(row.id, row.url, row.claim_type, row.snippet, row.confidence,
                           row.content_hash.decode("utf-8", "ignore"), row.observed_at)


class SqlEntityRepo:
    def __init__(self, session: Session):
        self.s = session

    def _to_dto(self, row: m.Entity) -> EntityRow:
        return EntityRow(
            row.id, row.entity_type, row.canonical_key, row.display_name,
            dict(row.attributes or {}), row.version, row.first_seen_at, row.last_seen_at,
        )

    def find_by_canonical(self, entity_type, canonical_key) -> EntityRow | None:
        if canonical_key is None:
            return None
        row = self.s.scalar(
            select(m.Entity).where(
                m.Entity.entity_type == entity_type, m.Entity.canonical_key == canonical_key
            )
        )
        return self._to_dto(row) if row else None

    def upsert_canonical(self, entity_type, canonical_key, display_name, attributes) -> EntityRow:
        row = self.s.scalar(
            select(m.Entity).where(
                m.Entity.entity_type == entity_type, m.Entity.canonical_key == canonical_key
            )
        )
        if row:
            row.attributes = {**(row.attributes or {}), **attributes}
            row.display_name = row.display_name or display_name
            row.last_seen_at = datetime.now(UTC)
            row.version += 1
        else:
            row = m.Entity(entity_type=entity_type, canonical_key=canonical_key,
                           display_name=display_name, attributes=attributes)
            self.s.add(row)
        self.s.flush()
        return self._to_dto(row)

    def create_blank(self, entity_type: str) -> EntityRow:
        row = m.Entity(entity_type=entity_type, attributes={})
        self.s.add(row)
        self.s.flush()
        return self._to_dto(row)

    def set_projection(self, entity_id, canonical_key, display_name, attributes) -> EntityRow:
        row = self.s.get(m.Entity, entity_id)
        if canonical_key:
            row.canonical_key = canonical_key
        row.display_name = display_name or row.display_name
        row.attributes = attributes
        row.last_seen_at = datetime.now(UTC)
        row.version += 1
        self.s.flush()
        return self._to_dto(row)

    def repoint(self, from_entity_id, to_entity_id) -> None:
        row = self.s.get(m.Entity, from_entity_id)
        if row:
            row.status = "merged"
            row.canonical_key = None  # free the unique key for the survivor
            row.attributes = {**(row.attributes or {}), "merged_into": to_entity_id}
            self.s.flush()

    def get(self, entity_id: int) -> EntityRow | None:
        row = self.s.get(m.Entity, entity_id)
        return self._to_dto(row) if row else None


class SqlSignalRepo:
    def __init__(self, session: Session):
        self.s = session

    def add(self, *, company_entity_id, signal_type, strength, intent_axis, evidence_ids,
            attributes) -> SignalRow:
        row = m.Signal(company_entity_id=company_entity_id, signal_type=signal_type,
                       strength=strength, intent_axis=intent_axis, evidence_ids=evidence_ids,
                       attributes=attributes)
        self.s.add(row)
        self.s.flush()
        return SignalRow(row.id, company_entity_id, signal_type, strength, intent_axis,
                         list(evidence_ids), row.detected_at, attributes)

    def for_company(self, company_entity_id: int) -> list[SignalRow]:
        rows = self.s.scalars(
            select(m.Signal).where(m.Signal.company_entity_id == company_entity_id)
        ).all()
        return [SignalRow(r.id, r.company_entity_id, r.signal_type, r.strength, r.intent_axis,
                          list(r.evidence_ids or []), r.detected_at, dict(r.attributes or {}))
                for r in rows]


class SqlOpportunityRepo:
    def __init__(self, session: Session):
        self.s = session

    def _to_dto(self, r: m.Opportunity) -> OpportunityRow:
        return OpportunityRow(
            id=r.id, company_entity_id=r.company_entity_id, tier=r.tier, template_id=r.template_id,
            thesis=r.thesis, opportunity_score=r.opportunity_score, department=r.department,
            decision_maker_role=r.decision_maker_role, person_entity_id=r.person_entity_id,
            primary_signal_id=r.primary_signal_id, status=r.status,
            evidence_ids=list(r.evidence_ids or []),
            created_at=r.created_at, updated_at=r.updated_at,
        )

    def find(self, company_entity_id, template_id) -> OpportunityRow | None:
        r = self.s.scalar(
            select(m.Opportunity).where(
                m.Opportunity.company_entity_id == company_entity_id,
                m.Opportunity.template_id == template_id,
            )
        )
        return self._to_dto(r) if r else None

    def upsert(self, row: OpportunityRow) -> OpportunityRow:
        r = self.s.scalar(
            select(m.Opportunity).where(
                m.Opportunity.company_entity_id == row.company_entity_id,
                m.Opportunity.template_id == row.template_id,
            )
        )
        if r is None:
            r = m.Opportunity(company_entity_id=row.company_entity_id, template_id=row.template_id)
            self.s.add(r)
        r.tier = row.tier
        r.thesis = row.thesis
        r.department = row.department
        r.decision_maker_role = row.decision_maker_role
        r.primary_signal_id = row.primary_signal_id
        r.opportunity_score = row.opportunity_score
        r.evidence_ids = row.evidence_ids
        r.updated_at = datetime.now(UTC)
        self.s.flush()
        return self._to_dto(r)

    def list(self, tier: str | None = None) -> list[OpportunityRow]:
        stmt = select(m.Opportunity)
        if tier and tier != "all":
            stmt = stmt.where(m.Opportunity.tier == tier)
        stmt = stmt.order_by(m.Opportunity.opportunity_score.desc())
        return [self._to_dto(r) for r in self.s.scalars(stmt).all()]

    def get(self, opportunity_id: int) -> OpportunityRow | None:
        r = self.s.get(m.Opportunity, opportunity_id)
        return self._to_dto(r) if r else None


class SqlBlockingRepo:
    def __init__(self, session: Session):
        self.s = session

    def add(self, entity_id: int, key_type: str, key_value: str) -> None:
        exists = self.s.scalar(
            select(m.BlockingKey.id).where(
                m.BlockingKey.entity_id == entity_id,
                m.BlockingKey.key_type == key_type,
                m.BlockingKey.key_value == key_value,
            )
        )
        if not exists:
            self.s.add(m.BlockingKey(entity_id=entity_id, key_type=key_type, key_value=key_value))
            self.s.flush()

    def candidates(self, keys) -> set[int]:
        if not keys:
            return set()
        conds = [(k.key_type, k.key_value) for k in keys]
        rows = self.s.scalars(
            select(m.BlockingKey.entity_id).where(
                tuple_key_in(conds)
            )
        ).all()
        return set(rows)


def tuple_key_in(conds):
    from sqlalchemy import tuple_

    return tuple_(m.BlockingKey.key_type, m.BlockingKey.key_value).in_(conds)


class SqlObservationRepo:
    def __init__(self, session: Session):
        self.s = session

    def add(self, **kw) -> ObservationRow:
        trust = kw.get("source_trust_tier", "community")
        # EntitySource has no trust column; stash it (survivorship skips __ keys).
        raw = {**kw["raw_attributes"], "__trust": trust}
        row = m.EntitySource(
            entity_id=kw["entity_id"], source_id=0, collector_id=0,
            external_id=kw.get("external_id"), raw_attributes=raw,
            evidence_id=kw["evidence_id"], match_prob=kw.get("match_prob"),
        )
        self.s.add(row)
        self.s.flush()
        return ObservationRow(
            id=row.id, entity_id=row.entity_id, source_slug=kw.get("source_slug", ""),
            source_trust_tier=trust, external_id=row.external_id,
            raw_attributes=dict(row.raw_attributes or {}),
            evidence_id=row.evidence_id, match_prob=row.match_prob, observed_at=row.observed_at,
        )

    def for_entity(self, entity_id: int) -> list[ObservationRow]:
        rows = self.s.scalars(
            select(m.EntitySource).where(m.EntitySource.entity_id == entity_id)
        ).all()
        return [ObservationRow(
            id=r.id, entity_id=r.entity_id, source_slug="",
            source_trust_tier=(r.raw_attributes or {}).get("__trust", "community"),
            external_id=r.external_id, raw_attributes=dict(r.raw_attributes or {}),
            evidence_id=r.evidence_id, match_prob=r.match_prob, observed_at=r.observed_at,
        ) for r in rows]

    def repoint(self, from_entity_id, to_entity_id) -> None:
        for r in self.s.scalars(
            select(m.EntitySource).where(m.EntitySource.entity_id == from_entity_id)
        ).all():
            r.entity_id = to_entity_id
        self.s.flush()


class SqlReviewRepo:
    def __init__(self, session: Session):
        self.s = session

    def add(self, left_entity, right_entity, match_prob, features) -> ReviewRow:
        row = m.ResolutionReview(left_entity=left_entity, right_entity=right_entity,
                                 match_prob=match_prob, features=features)
        self.s.add(row)
        self.s.flush()
        return ReviewRow(row.id, left_entity, right_entity, match_prob, features, None)

    def pending(self) -> list[ReviewRow]:
        rows = self.s.scalars(
            select(m.ResolutionReview).where(m.ResolutionReview.decision.is_(None))
        ).all()
        return [ReviewRow(r.id, r.left_entity, r.right_entity, r.match_prob,
                          dict(r.features or {}), r.decision) for r in rows]

    def get(self, review_id: int) -> ReviewRow | None:
        r = self.s.get(m.ResolutionReview, review_id)
        return ReviewRow(r.id, r.left_entity, r.right_entity, r.match_prob,
                         dict(r.features or {}), r.decision) if r else None


class SqlMergeRepo:
    def __init__(self, session: Session):
        self.s = session

    def add(self, **kw) -> MergeRow:
        row = m.EntityMerge(
            surviving_entity_id=kw["surviving_entity_id"],
            merged_entity_id=kw["merged_entity_id"], method=kw["method"],
            confidence=kw["confidence"], features=kw.get("features", {}),
        )
        self.s.add(row)
        self.s.flush()
        return MergeRow(row.id, row.surviving_entity_id, row.merged_entity_id,
                        row.method, row.confidence, dict(row.features or {}))

    def all(self) -> list[MergeRow]:
        rows = self.s.scalars(select(m.EntityMerge)).all()
        return [MergeRow(r.id, r.surviving_entity_id, r.merged_entity_id, r.method,
                         r.confidence, dict(r.features or {})) for r in rows]
