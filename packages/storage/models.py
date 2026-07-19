"""Core ORM models (spec 01 / docs/schema/schema.sql).

A pragmatic first slice: reference/config, evidence, entity core + satellites,
graph edges, signals, opportunities, and scores. Additional tables (blocking_key,
resolution_review, timeline_event partitions, ops) are added as their workers land.
The DDL source of truth remains Alembic migrations.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, utcnow

# ---------------------------------------------------------------- reference / config


class Source(Base):
    __tablename__ = "source"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    trust_tier: Mapped[str] = mapped_column(String, default="community")
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Collector(Base):
    __tablename__ = "collector"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"))
    slug: Mapped[str] = mapped_column(String, unique=True)
    version: Mapped[str] = mapped_column(String)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- evidence (partition parent)


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_evidence_conf"),
        Index("evidence_claim_idx", "claim_type", "observed_at"),
        Index("evidence_hash_idx", "content_hash"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger)
    collector_id: Mapped[int] = mapped_column(BigInteger)
    raw_document_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary)
    claim_type: Mapped[str] = mapped_column(String)
    claim: Mapped[dict] = mapped_column(JSONB, default=dict)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- entity core


class Entity(Base):
    __tablename__ = "entity"
    __table_args__ = (
        UniqueConstraint("entity_type", "canonical_key", name="uq_entity_type_key"),
        Index("entity_type_idx", "entity_type", "status"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String)
    canonical_key: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String, default="active")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class EntitySource(Base):
    __tablename__ = "entity_source"
    __table_args__ = (
        Index("entity_source_entity_idx", "entity_id", "observed_at"),
        Index("entity_source_ext_idx", "source_id", "external_id"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    source_id: Mapped[int] = mapped_column(BigInteger)
    collector_id: Mapped[int] = mapped_column(BigInteger)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_id: Mapped[int] = mapped_column(BigInteger)
    match_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Company(Base):
    __tablename__ = "company"
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), primary_key=True)
    primary_domain: Mapped[str | None] = mapped_column(String, nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    employee_range: Mapped[str | None] = mapped_column(String, nullable=True)
    hq_country: Mapped[str | None] = mapped_column(String, nullable=True)
    funding_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    tech_stack: Mapped[list] = mapped_column(JSONB, default=list)


class Person(Base):
    __tablename__ = "person"
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    current_company_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True)
    current_role: Mapped[str | None] = mapped_column(String, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String, nullable=True)
    headline: Mapped[str | None] = mapped_column(String, nullable=True)


# ---------------------------------------------------------------- graph


class Edge(Base):
    __tablename__ = "edge"
    __table_args__ = (
        UniqueConstraint(
            "src_entity_id", "dst_entity_id", "edge_type", "valid_from", name="uq_edge"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_edge_conf"),
        CheckConstraint("cardinality(evidence_ids) > 0", name="ck_edge_evidence"),
        Index("edge_src_idx", "src_entity_id", "edge_type"),
        Index("edge_dst_idx", "dst_entity_id", "edge_type"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    src_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    dst_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    edge_type: Mapped[str] = mapped_column(String)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    derived: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- signals / opportunities


class Signal(Base):
    __tablename__ = "signal"
    __table_args__ = (
        CheckConstraint("strength >= 0 AND strength <= 1", name="ck_signal_strength"),
        Index("signal_company_idx", "company_entity_id", "signal_type", "detected_at"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    person_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True)
    signal_type: Mapped[str] = mapped_column(String)
    strength: Mapped[float] = mapped_column(Float, default=0.5)
    intent_axis: Mapped[str | None] = mapped_column(String, nullable=True)
    decayed_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Opportunity(Base):
    __tablename__ = "opportunity"
    __table_args__ = (
        UniqueConstraint("company_entity_id", "template_id", name="uq_opp_company_template"),
        Index("opportunity_tier_score_idx", "tier", "opportunity_score"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    person_entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True)
    tier: Mapped[str] = mapped_column(String, default="bronze")
    template_id: Mapped[str | None] = mapped_column(String, nullable=True)
    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_maker_role: Mapped[str | None] = mapped_column(String, nullable=True)
    primary_signal_id: Mapped[int | None] = mapped_column(ForeignKey("signal.id"), nullable=True)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    status: Mapped[str] = mapped_column(String, default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    transitions: Mapped[list[OpportunityTransition]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class OpportunityTransition(Base):
    __tablename__ = "opportunity_transition"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunity.id"))
    from_tier: Mapped[str | None] = mapped_column(String, nullable=True)
    to_tier: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    opportunity: Mapped[Opportunity] = relationship(back_populates="transitions")


class TimelineEvent(Base):
    __tablename__ = "timeline_event"
    # Monthly RANGE-partitioned (migration 0003): the partition column is part of
    # the primary key, as Postgres requires for partitioned tables.
    __table_args__ = (Index("timeline_company_idx", "company_entity_id", "occurred_at"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    event_type: Mapped[str] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signal.id"), nullable=True)
    evidence_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, default=utcnow
    )


class Score(Base):
    __tablename__ = "score"
    subject_kind: Mapped[str] = mapped_column(String, primary_key=True)
    subject_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    score_type: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSONB, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- entity resolution (M1)


class BlockingKey(Base):
    __tablename__ = "blocking_key"
    __table_args__ = (
        UniqueConstraint("entity_id", "key_type", "key_value", name="uq_blocking_key"),
        Index("blocking_key_lookup", "key_type", "key_value"),
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    key_type: Mapped[str] = mapped_column(String)
    key_value: Mapped[str] = mapped_column(String)


class ResolutionReview(Base):
    __tablename__ = "resolution_review"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    left_entity: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    right_entity: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    match_prob: Mapped[float] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
    decision: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EntityMerge(Base):
    __tablename__ = "entity_merge"
    __table_args__ = (Index("entity_merge_surv_idx", "surviving_entity_id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    surviving_entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"))
    merged_entity_id: Mapped[int] = mapped_column(BigInteger)
    method: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "Source",
    "Collector",
    "Evidence",
    "Entity",
    "EntitySource",
    "Company",
    "Person",
    "Edge",
    "Signal",
    "Opportunity",
    "OpportunityTransition",
    "Score",
    "BlockingKey",
    "ResolutionReview",
    "EntityMerge",
    "TimelineEvent",
]
