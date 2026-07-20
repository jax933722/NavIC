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
    person_name: str | None = None  # set for Gold (resolved decision maker)
    # Qualifying detail lifted from a service request (budget, timeline, stack, ...).
    qualifiers: dict | None = None
    evidence_refs: list[EvidenceRef] = []
    updated_at: datetime


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = 50


class OpportunityList(BaseModel):
    data: list[OpportunityCard]
    page: Page


class TransitionOut(BaseModel):
    from_tier: str | None
    to_tier: str
    reason: str | None
    score_delta: float | None
    created_at: datetime


class TimelineEventOut(BaseModel):
    event_type: str
    summary: str | None
    occurred_at: datetime


class CompanyDetail(BaseModel):
    id: int
    name: str | None
    domain: str | None
    attributes: dict
    signals: int
    opportunities: list[OpportunityCard]
    timeline: list[TimelineEventOut]


class SearchResultOut(BaseModel):
    type: str
    id: int
    name: str | None
    domain: str | None
    score: float
    tier: str | None = None
    matched_on: list[str] = []
    evidence_refs: list[EvidenceRef] = []


class SearchResponse(BaseModel):
    data: list[SearchResultOut]
    interpreted: dict
    page: Page


class SeedRequest(BaseModel):
    urls: list[str]


class SeedResponse(BaseModel):
    fetched: int
    companies: int
    signals: int
    opportunities: int
    transitions: int


class CaptureRequest(BaseModel):
    """A post/text an operator saw and chose to save (human-in-the-loop, no scraping)."""

    text: str
    company_domain: str  # the buyer's company site/domain (anchors the opportunity)
    company_name: str | None = None
    author_name: str | None = None
    author_role: str | None = None
    source_url: str | None = None  # link back to the post (evidence)


class CaptureResponse(BaseModel):
    companies: int
    signals: int
    detected_signals: list[str]
    opportunities: list[OpportunityCard]
