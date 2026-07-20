"""NavIC API — read surface + search + digest + seed (spec 06).

Datastore-agnostic: every endpoint works against a RepoBundle from the configured
provider (in-memory by default, Postgres when NAVIC_API_BACKEND=postgres). The
endpoint code never changes between backends — the interface/adapter payoff.

Auth-less by design in v1 (single operator, network-isolated). The SaaS seam is
middleware + a tenant filter later (blueprint §27) — no endpoint changes.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
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
    ImportResponse,
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


def _contact(r: RepoBundle, company_id: int) -> dict | None:
    """Best-known contact at the company: a linked person, preferring one with an
    email (e.g. supplied via import). Returns {name, email, role} or None."""
    best: dict | None = None
    for edge in r.edges.in_edges(company_id, "works_at"):
        person = r.entities.get(edge.src_entity_id)
        if person is None:
            continue
        cand = {"name": person.display_name or person.attributes.get("full_name"),
                "email": person.attributes.get("email"),
                "role": (edge.attributes or {}).get("role")
                or person.attributes.get("current_role")}
        if cand["email"]:
            return cand
        best = best or cand
    return best


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
        contact=_contact(r, opp.company_entity_id),
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


def _lead_candidates(*, text: str, company_domain: str, company_name: str | None = None,
                     author_name: str | None = None, author_role: str | None = None,
                     source_url: str | None = None, email: str | None = None) -> tuple:
    """Build (apex, candidates) for one lead: a company, an optional contact person
    (with email if supplied), and any buying signals in the text. Shared by the
    Capture (paste one) and Import (spreadsheet) paths. Returns (None, []) if the
    company domain doesn't resolve."""
    apex = apex_domain(company_domain or "")
    if not apex:
        return None, []
    ev_url = source_url or f"https://{apex}"
    name = company_name or apex
    text = (text or "").strip()

    candidates = [build_candidate(
        kind="entity", entity_type="company",
        attributes={"name": name, "display_name": name, "primary_domain": apex,
                    "canonical_key": apex},
        evidence=EvidenceDraft(url=ev_url, claim_type="company.domain",
                               snippet=(text or name)[:200], confidence=0.7),
        blocking_hints={"apex_domain": apex})]

    if author_name:
        attrs = {"full_name": author_name, "name": author_name, "current_role": author_role,
                 "company_apex": apex, "company_domain": apex}
        if email:
            attrs["email"] = email
        candidates.append(build_candidate(
            kind="entity", entity_type="person", attributes=attrs,
            evidence=EvidenceDraft(url=ev_url, claim_type="person.role",
                                   snippet=f"{author_name} — {author_role or ''}".strip(),
                                   confidence=0.7),
            blocking_hints={"name": author_name, "company_apex": apex}))

    if text:
        candidates.extend(detect_signals(text, ev_url, apex))
    return apex, candidates


@app.post("/v1/admin/capture", response_model=CaptureResponse)
def capture(req: CaptureRequest) -> CaptureResponse:
    """Human-in-the-loop capture: an operator pastes a post they saw and it becomes an
    evidence-backed opportunity. No scraping — a person chooses each item. Free and
    fully within source terms (it's just a human submitting text they lawfully read)."""
    apex, candidates = _lead_candidates(
        text=req.text, company_domain=req.company_domain, company_name=req.company_name,
        author_name=req.author_name, author_role=req.author_role, source_url=req.source_url)
    if apex is None:
        raise HTTPException(status_code=422,
                            detail="a valid company website/domain is required (e.g. acme.com)")

    with app.state.provider.bundle() as r:
        result = r.pipeline.ingest(candidates, content_hash=req.source_url or f"https://{apex}")
        cards = [_card(r, o) for o in result.opportunities]
    return CaptureResponse(
        companies=result.companies,
        signals=result.signals,
        detected_signals=[c.signal_type for c in candidates if c.kind == "signal"],
        opportunities=cards,
    )


# Accepted spreadsheet headers -> canonical field (case/space-insensitive match).
_IMPORT_HEADERS = {
    "name": "name", "full name": "name", "fullname": "name", "contact": "name",
    "contact name": "name", "person": "name",
    "company domain": "domain", "domain": "domain", "website": "domain",
    "company": "domain", "company url": "domain", "company website": "domain", "url": "domain",
    "requirement": "requirement", "requirements": "requirement", "need": "requirement",
    "request": "requirement", "notes": "requirement", "note": "requirement",
    "post": "requirement", "description": "requirement", "message": "requirement",
    "email": "email", "email address": "email", "e-mail": "email", "mail": "email",
    "role": "role", "title": "role", "job title": "role",
}


def _rows_from_upload(filename: str, blob: bytes) -> list[dict]:
    """Parse .xlsx or .csv bytes into a list of {name, domain, requirement, email, role}."""
    name = (filename or "").lower()
    if name.endswith(".csv") or (not name.endswith(".xlsx") and b"," in blob[:4096]):
        import csv
        text = blob.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        table = [list(row) for row in reader]
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
        ws = wb.active
        table = [[("" if c is None else str(c)) for c in row]
                 for row in ws.iter_rows(values_only=True)]
    if not table:
        return []
    header = [(_IMPORT_HEADERS.get((h or "").strip().lower())) for h in table[0]]
    rows: list[dict] = []
    for raw in table[1:]:
        if not any(str(c).strip() for c in raw):
            continue
        rec: dict = {}
        for i, field in enumerate(header):
            if field and i < len(raw):
                rec[field] = str(raw[i]).strip()
        rows.append(rec)
    return rows


@app.post("/v1/admin/import", response_model=ImportResponse)
async def import_leads(file: UploadFile = File(...)) -> ImportResponse:  # noqa: B008
    """Bulk import leads from an Excel (.xlsx) or CSV file. Columns (flexible headers):
    name, company domain, requirement, email (optional), role (optional). Each row's
    requirement is classified like a captured post; the contact (name/email) is kept."""
    blob = await file.read()
    try:
        rows = _rows_from_upload(file.filename or "", blob)
    except Exception as exc:  # noqa: BLE001  (surface any parse failure to the operator)
        raise HTTPException(status_code=422, detail=f"could not read the file: {exc}") from exc
    if not rows:
        raise HTTPException(
            status_code=422,
            detail="no data rows found — need a header row with a 'company domain' column")

    imported = skipped = companies = signals = opps = 0
    errors: list[str] = []
    with app.state.provider.bundle() as r:
        for n, rec in enumerate(rows, start=2):  # row 1 is the header
            apex, candidates = _lead_candidates(
                text=rec.get("requirement", ""), company_domain=rec.get("domain", ""),
                author_name=rec.get("name"), author_role=rec.get("role"),
                email=rec.get("email"))
            if apex is None:
                skipped += 1
                errors.append(f"row {n}: missing/invalid company domain")
                continue
            result = r.pipeline.ingest(candidates, content_hash=f"import:{apex}:{n}")
            imported += 1
            companies += result.companies
            signals += result.signals
            opps += len(result.opportunities)
    return ImportResponse(rows=len(rows), imported=imported, skipped=skipped,
                          companies=companies, signals=signals, opportunities=opps,
                          row_errors=errors[:50])
