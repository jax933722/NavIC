"""NavIC API — read surface + search + digest + seed (spec 06).

Datastore-agnostic: every endpoint works against a RepoBundle from the configured
provider (in-memory by default, Postgres when NAVIC_API_BACKEND=postgres). The
endpoint code never changes between backends — the interface/adapter payoff.

Auth-less by design in v1 (single operator, network-isolated). The SaaS seam is
middleware + a tenant filter later (blueprint §27) — no endpoint changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from core.errors import NavicError
from extraction import EvidenceDraft, build_candidate
from ingestion import HttpFetchClient
from normalization import apex_domain
from opportunities import build_digest
from pipeline import ingest_company_web_urls
from search import SearchService
from signals import detect_signals

from .repos import RepoBundle, get_provider
from .schemas import (
    CaptureRequest,
    CaptureResponse,
    CompanyDetail,
    CompanyRef,
    EvidenceRef,
    OpportunityCard,
    OpportunityList,
    Page,
    SearchResponse,
    SearchResultOut,
    SeedRequest,
    SeedResponse,
    TimelineEventOut,
    TransitionOut,
)

app = FastAPI(title="NavIC API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.state.provider = get_provider()


def _evidence_refs(r: RepoBundle, ids: list[int]) -> list[EvidenceRef]:
    refs = []
    for eid in ids:
        row = r.evidence.get(eid)
        if row:
            refs.append(EvidenceRef(
                id=row.id, url=row.url, claim_type=row.claim_type, snippet=row.snippet,
                confidence=row.confidence, observed_at=row.observed_at,
            ))
    return refs


def _company_ref(r: RepoBundle, company_id: int) -> CompanyRef:
    ent = r.entities.get(company_id)
    if ent is None:
        return CompanyRef(id=company_id, name=None, domain=None)
    return CompanyRef(id=ent.id, name=ent.display_name or ent.attributes.get("name"),
                      domain=ent.attributes.get("primary_domain"))


_QUALIFIER_KEYS = ("service", "budget", "timeline", "engagement", "remote", "stack")


def _qualifiers(r: RepoBundle, opp) -> dict | None:
    """Lift the request's qualifying detail (budget/timeline/stack/...) off the
    opportunity's primary signal, for solicitation-driven opportunities."""
    sig_id = getattr(opp, "primary_signal_id", None)
    if not sig_id:
        return None
    signal = next((s for s in r.signals.for_company(opp.company_entity_id) if s.id == sig_id),
                  None)
    if signal is None or signal.signal_type != "solicitation":
        return None
    out = {k: signal.attributes[k] for k in _QUALIFIER_KEYS if signal.attributes.get(k)}
    return out or None


def _card(r: RepoBundle, opp) -> OpportunityCard:
    person_name = None
    if opp.person_entity_id:
        person = r.entities.get(opp.person_entity_id)
        if person:
            person_name = person.display_name or person.attributes.get("full_name")
    return OpportunityCard(
        id=opp.id, tier=opp.tier, thesis=opp.thesis,
        company=_company_ref(r, opp.company_entity_id),
        opportunity_score=round(opp.opportunity_score, 4),
        department=opp.department, decision_maker_role=opp.decision_maker_role,
        person_name=person_name, qualifiers=_qualifiers(r, opp),
        evidence_refs=_evidence_refs(r, opp.evidence_ids),
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
    with app.state.provider.bundle() as r:
        rows = r.opportunities.list(tier=tier)[:limit]
        return OpportunityList(data=[_card(r, x) for x in rows],
                               page=Page(has_more=False, limit=limit))


@app.get("/v1/opportunities/{opportunity_id}", response_model=OpportunityCard)
def get_opportunity(opportunity_id: int) -> OpportunityCard:
    with app.state.provider.bundle() as r:
        opp = r.opportunities.get(opportunity_id)
        if opp is None:
            raise HTTPException(status_code=404, detail="opportunity not found")
        return _card(r, opp)


@app.get("/v1/opportunities/{opportunity_id}/transitions", response_model=list[TransitionOut])
def opportunity_transitions(opportunity_id: int) -> list[TransitionOut]:
    with app.state.provider.bundle() as r:
        rows = r.transitions.for_opportunity(opportunity_id)
        return [TransitionOut(from_tier=t.from_tier, to_tier=t.to_tier, reason=t.reason,
                              score_delta=t.score_delta, created_at=t.created_at) for t in rows]


@app.get("/v1/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: int) -> CompanyDetail:
    with app.state.provider.bundle() as r:
        ent = r.entities.get(company_id)
        if ent is None or ent.entity_type != "company":
            raise HTTPException(status_code=404, detail="company not found")
        opps = [o for o in r.opportunities.list() if o.company_entity_id == company_id]
        timeline = [
            TimelineEventOut(event_type=e.event_type, summary=e.summary, occurred_at=e.occurred_at)
            for e in r.timeline.for_company(company_id)
        ]
        return CompanyDetail(
            id=ent.id, name=ent.display_name or ent.attributes.get("name"),
            domain=ent.attributes.get("primary_domain"), attributes=ent.attributes,
            signals=len(r.signals.for_company(company_id)),
            opportunities=[_card(r, o) for o in opps], timeline=timeline,
        )


@app.get("/v1/companies/{company_id}/graph")
def company_graph(company_id: int, depth: int = Query(1, ge=1, le=2)) -> dict:
    """1–2 hop neighborhood of a company (spec 02 §7.1)."""
    with app.state.provider.bundle() as r:
        root = r.entities.get(company_id)
        if root is None:
            raise HTTPException(status_code=404, detail="company not found")
        nodes: dict[int, dict] = {}
        edges: list[dict] = []

        def add_node(ent):
            if ent and ent.id not in nodes:
                nodes[ent.id] = {"id": ent.id, "type": ent.entity_type,
                                 "label": ent.display_name or ent.attributes.get("name")
                                 or ent.attributes.get("full_name") or str(ent.id)}

        add_node(root)
        frontier = [company_id]
        for _ in range(depth):
            nxt = []
            for nid in frontier:
                for e in r.edges.in_edges(nid) + r.edges.out_edges(nid):
                    src, dst = r.entities.get(e.src_entity_id), r.entities.get(e.dst_entity_id)
                    add_node(src)
                    add_node(dst)
                    edges.append({"type": e.edge_type, "from": e.src_entity_id,
                                  "to": e.dst_entity_id, "confidence": e.confidence,
                                  "evidence_ids": e.evidence_ids})
                    nxt += [e.src_entity_id, e.dst_entity_id]
            frontier = nxt
        # dedupe edges
        seen = set()
        uniq = []
        for e in edges:
            k = (e["from"], e["to"], e["type"])
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        return {"nodes": list(nodes.values()), "edges": uniq}


@app.get("/v1/evidence/{evidence_id}", response_model=EvidenceRef)
def get_evidence(evidence_id: int) -> EvidenceRef:
    with app.state.provider.bundle() as r:
        row = r.evidence.get(evidence_id)
        if row is None:
            raise HTTPException(status_code=404, detail="evidence not found")
        return EvidenceRef(id=row.id, url=row.url, claim_type=row.claim_type, snippet=row.snippet,
                           confidence=row.confidence, observed_at=row.observed_at)


@app.get("/v1/digest")
def digest(days: int = 1) -> dict:
    with app.state.provider.bundle() as r:
        since = datetime.now(UTC) - timedelta(days=days)
        d = build_digest(opportunities=r.opportunities, transitions=r.transitions,
                         entities=r.entities, since=since)
        return {
            "generated_at": d.generated_at.isoformat(), "since": d.since.isoformat(),
            "total": d.total, "new": [i.__dict__ for i in d.new],
            "upgraded": [i.__dict__ for i in d.upgraded],
        }


@app.get("/v1/search", response_model=SearchResponse)
def search(q: str, limit: int = 25) -> SearchResponse:
    with app.state.provider.bundle() as r:
        svc = SearchService(entities=r.entities, signals=r.signals,
                            opportunities=r.opportunities, edges=r.edges, evidence=r.evidence)
        intent, results = svc.search(q, limit=limit)
        data = [
            SearchResultOut(type=x.type, id=x.id, name=x.name, domain=x.domain, score=x.score,
                            tier=x.tier, matched_on=x.matched_on,
                            evidence_refs=_evidence_refs(r, x.evidence_ids))
            for x in results
        ]
        return SearchResponse(
            data=data,
            interpreted={"structured_filters": intent.filters_found,
                         "free_text": intent.free_text, "target": intent.target},
            page=Page(has_more=False, limit=limit),
        )


@app.get("/v1/admin/collectors")
def list_collectors() -> dict:
    """Registered collectors + capabilities (ops page, spec 07 §3.7)."""
    import collectors.sources  # noqa: F401  (ensure registration)
    from collectors import REGISTRY

    out = []
    for slug, cls in sorted(REGISTRY.items()):
        caps = getattr(cls, "capabilities", None)
        out.append({
            "collector": slug,
            "source": getattr(cls, "source_slug", None),
            "version": getattr(cls, "version", None),
            "capabilities": caps.__dict__ if caps else {},
        })
    return {"data": out}


def _entity_summary(r: RepoBundle, entity_id: int) -> dict:
    ent = r.entities.get(entity_id)
    if ent is None:
        return {"id": entity_id}
    return {"id": ent.id, "type": ent.entity_type,
            "name": ent.display_name or ent.attributes.get("name"),
            "domain": ent.attributes.get("primary_domain"),
            "attributes": {k: v for k, v in ent.attributes.items()
                           if not k.endswith("__provenance") and not k.startswith("__")}}


@app.get("/v1/admin/resolution/review")
def list_reviews() -> dict:
    """Pending borderline merge pairs for operator adjudication (spec 04 §11)."""
    with app.state.provider.bundle() as r:
        out = []
        for review in r.reviews.pending():
            out.append({
                "id": review.id, "match_prob": round(review.match_prob, 4),
                "features": review.features,
                "left": _entity_summary(r, review.left_entity),
                "right": _entity_summary(r, review.right_entity),
            })
        return {"data": out}


@app.post("/v1/admin/resolution/{review_id}/decide")
def decide_review(review_id: int, decision: str = Query(..., pattern="^(merge|no_match)$")) -> dict:
    with app.state.provider.bundle() as r:
        engine = r.resolution_engine()
        engine.decide_review(review_id, decision)
        return {"review_id": review_id, "decision": decision, "status": "ok"}


@app.post("/v1/admin/seed", response_model=SeedResponse)
def seed(req: SeedRequest) -> SeedResponse:
    """Run the company_web collector over URLs and ingest the results (dev/demo)."""
    with app.state.provider.bundle() as r:
        try:
            summary = ingest_company_web_urls(req.urls, pipeline=r.pipeline,
                                              fetch=HttpFetchClient())
        except NavicError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return SeedResponse(**summary.__dict__)


@app.post("/v1/admin/capture", response_model=CaptureResponse)
def capture(req: CaptureRequest) -> CaptureResponse:
    """Human-in-the-loop capture: an operator pastes a post they saw and it becomes an
    evidence-backed opportunity. No scraping — a person chooses each item. Free and
    fully within source terms (it's just a human submitting text they lawfully read)."""
    apex = apex_domain(req.company_domain)
    if not apex:
        raise HTTPException(status_code=422,
                            detail="a valid company website/domain is required (e.g. acme.com)")
    ev_url = req.source_url or f"https://{apex}"
    name = req.company_name or apex
    snippet = req.text.strip()[:200]

    candidates = [build_candidate(
        kind="entity", entity_type="company",
        attributes={"name": name, "display_name": name, "primary_domain": apex,
                    "canonical_key": apex},
        evidence=EvidenceDraft(url=ev_url, claim_type="company.domain",
                               snippet=snippet, confidence=0.7),
        blocking_hints={"apex_domain": apex})]

    if req.author_name:
        candidates.append(build_candidate(
            kind="entity", entity_type="person",
            attributes={"full_name": req.author_name, "name": req.author_name,
                        "current_role": req.author_role, "company_apex": apex,
                        "company_domain": apex},
            evidence=EvidenceDraft(url=ev_url, claim_type="person.role",
                                   snippet=f"{req.author_name} — {req.author_role or ''}".strip(),
                                   confidence=0.7),
            blocking_hints={"name": req.author_name, "company_apex": apex}))

    candidates.extend(detect_signals(req.text, ev_url, apex))

    with app.state.provider.bundle() as r:
        result = r.pipeline.ingest(candidates, content_hash=ev_url)
        cards = [_card(r, o) for o in result.opportunities]
    return CaptureResponse(
        companies=result.companies,
        signals=result.signals,
        detected_signals=[c.signal_type for c in candidates if c.kind == "signal"],
        opportunities=cards,
    )
