"""API response models (subset of spec 06). Every entity/opportunity embeds
its evidence refs — trust is the product (principle A2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EvidenceRef(BaseModel):
    id: int
    url: str
    claim_type: str
    snippet: str | None
    confidence: float
    observed_at: datetime


class CompanyRef(BaseModel):
    id: int
    name: str | None
    domain: str | None


class OpportunityCard(BaseModel):
    id: int
    tier: str
    thesis: str | None
    company: CompanyRef
    opportunity_score: float
    department: str | None = None
    decision_maker_role: str | None = None
    evidence_refs: list[EvidenceRef] = []
    updated_at: datetime


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 50


class OpportunityList(BaseModel):
    data: list[OpportunityCard]
    page: Page


class CompanyDetail(BaseModel):
    id: int
    name: str | None
    domain: str | None
    attributes: dict
    signals: int
    opportunities: list[OpportunityCard]


class SeedRequest(BaseModel):
    urls: list[str]


class SeedResponse(BaseModel):
    fetched: int
    companies: int
    signals: int
    opportunities: int
    transitions: int
