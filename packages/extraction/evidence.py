"""Evidence + candidate models (specs 03 §2.1, 04, blueprint invariant I2).

Every extracted claim must reference evidence (url, snippet, claim_type,
confidence). The type system encodes this: ``build_candidate`` refuses to
produce a candidate without a valid ``EvidenceDraft``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from core.errors import EvidenceRequired


class EvidenceDraft(BaseModel):
    """A single sourced claim, before it is persisted to the evidence table."""

    url: str
    claim_type: str
    snippet: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("url", "claim_type")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("evidence url and claim_type must be non-empty")
        return v.strip()


class CandidateRecord(BaseModel):
    """A candidate entity or signal emitted by a collector/extractor.

    ``evidence`` is mandatory — invariant I2.
    """

    kind: str  # 'entity' | 'signal'
    entity_type: str | None = None
    signal_type: str | None = None
    attributes: dict = Field(default_factory=dict)
    evidence: EvidenceDraft
    blocking_hints: dict = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _valid_kind(cls, v: str) -> str:
        if v not in ("entity", "signal"):
            raise ValueError("kind must be 'entity' or 'signal'")
        return v


def build_candidate(
    *,
    kind: str,
    evidence: EvidenceDraft | None,
    entity_type: str | None = None,
    signal_type: str | None = None,
    attributes: dict | None = None,
    blocking_hints: dict | None = None,
) -> CandidateRecord:
    """Construct a candidate, enforcing the no-claim-without-evidence invariant."""
    if evidence is None:
        raise EvidenceRequired("a candidate claim cannot be created without evidence (I2)")
    return CandidateRecord(
        kind=kind,
        entity_type=entity_type,
        signal_type=signal_type,
        attributes=attributes or {},
        evidence=evidence,
        blocking_hints=blocking_hints or {},
    )
