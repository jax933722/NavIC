"""NavIC API — M0 read surface + seed endpoint (spec 06).

REST endpoints over the repository layer:
  GET  /v1/opportunities?tier=          board (the dashboard's core)
  GET  /v1/opportunities/{id}           full card
  GET  /v1/companies/{id}               firmographics + rollups
  GET  /v1/evidence/{id}                provenance
  POST /v1/admin/seed                   run company_web over URLs (demo/dev)

Auth-less by design in v1 (single operator, network-isolated). The SaaS seam is
middleware + a tenant filter later (blueprint §27) — no endpoint changes.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from core.errors import NavicError
from ingestion import HttpFetchClient
from pipeline import ingest_company_web_urls

from .schemas import (
    CompanyDetail,
    CompanyRef,
    EvidenceRef,
    OpportunityCard,
    OpportunityList,
    Page,
    SeedRequest,
    SeedResponse,
    TimelineEventOut,
    TransitionOut,
)
from .state import AppState, new_state

app = FastAPI(title="NavIC API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # internal single-operator tool
    allow_methods=["*"],
    allow_headers=["*"],
)

# One process-wide state for M0 (in-memory repos). Swapped for DB-backed repos
# via a FastAPI dependency once the stack is up; tests override this attribute.
app.state.app_state = new_state()


def _state() -> AppState:
    return app.state.app_state


def _evidence_refs(state: AppState, ids: list[int]) -> list[EvidenceRef]:
    refs = []
    for eid in ids:
        row = state.evidence.get(eid)
        if row:
            refs.append(
                EvidenceRef(
                    id=row.id, url=row.url, claim_type=row.claim_type, snippet=row.snippet,
                    confidence=row.confidence, observed_at=row.observed_at,
                )
            )
    return refs


def _company_ref(state: AppState, company_id: int) -> CompanyRef:
    ent = state.entities.get(company_id)
    if ent is None:
        return CompanyRef(id=company_id, name=None, domain=None)
    return CompanyRef(
        id=ent.id,
        name=ent.display_name or ent.attributes.get("name"),
        domain=ent.attributes.get("primary_domain"),
    )


def _card(state: AppState, opp) -> OpportunityCard:
    person_name = None
    if opp.person_entity_id:
        person = state.entities.get(opp.person_entity_id)
        if person:
            person_name = person.display_name or person.attributes.get("full_name")
    return OpportunityCard(
        id=opp.id,
        tier=opp.tier,
        thesis=opp.thesis,
        company=_company_ref(state, opp.company_entity_id),
        opportunity_score=round(opp.opportunity_score, 4),
        department=opp.department,
        decision_maker_role=opp.decision_maker_role,
        person_name=person_name,
        evidence_refs=_evidence_refs(state, opp.evidence_ids),
        updated_at=opp.updated_at,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/opportunities", response_model=OpportunityList)
def list_opportunities(
    tier: str = Query("all", pattern="^(all|gold|silver|bronze)$"),
    limit: int = Query(50, ge=1, le=200),
) -> OpportunityList:
    state = _state()
    rows = state.opportunities.list(tier=tier)[:limit]
    return OpportunityList(
        data=[_card(state, r) for r in rows],
        page=Page(has_more=False, limit=limit),
    )


@app.get("/v1/opportunities/{opportunity_id}", response_model=OpportunityCard)
def get_opportunity(opportunity_id: int) -> OpportunityCard:
    state = _state()
    opp = state.opportunities.get(opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return _card(state, opp)


@app.get("/v1/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int) -> CompanyDetail:
    state = _state()
    ent = state.entities.get(company_id)
    if ent is None or ent.entity_type != "company":
        raise HTTPException(status_code=404, detail="company not found")
    opps = [o for o in state.opportunities.list() if o.company_entity_id == company_id]
    timeline = [
        TimelineEventOut(event_type=e.event_type, summary=e.summary, occurred_at=e.occurred_at)
        for e in state.timeline.for_company(company_id)
    ]
    return CompanyDetail(
        id=ent.id,
        name=ent.display_name or ent.attributes.get("name"),
        domain=ent.attributes.get("primary_domain"),
        attributes=ent.attributes,
        signals=len(state.signals.for_company(company_id)),
        opportunities=[_card(state, o) for o in opps],
        timeline=timeline,
    )


@app.get("/v1/opportunities/{opportunity_id}/transitions", response_model=list[TransitionOut])
def opportunity_transitions(opportunity_id: int) -> list[TransitionOut]:
    state = _state()
    rows = state.transitions.for_opportunity(opportunity_id)
    return [
        TransitionOut(from_tier=r.from_tier, to_tier=r.to_tier, reason=r.reason,
                      score_delta=r.score_delta, created_at=r.created_at)
        for r in rows
    ]


@app.get("/v1/evidence/{evidence_id}", response_model=EvidenceRef)
def get_evidence(evidence_id: int) -> EvidenceRef:
    state = _state()
    row = state.evidence.get(evidence_id)
    if row is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return EvidenceRef(
        id=row.id, url=row.url, claim_type=row.claim_type, snippet=row.snippet,
        confidence=row.confidence, observed_at=row.observed_at,
    )


@app.post("/v1/admin/seed", response_model=SeedResponse)
def seed(req: SeedRequest) -> SeedResponse:
    """Run the company_web collector over URLs and ingest the results (dev/demo)."""
    state = _state()
    try:
        summary = ingest_company_web_urls(
            req.urls, pipeline=state.pipeline, fetch=HttpFetchClient()
        )
    except NavicError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SeedResponse(**summary.__dict__)
