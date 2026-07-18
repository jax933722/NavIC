# 06 — Backend API Specification

> **Master spec:** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §17 (API) + §16 (Search) · Frontend consumer: [`07-frontend-uiux.md`](./07-frontend-uiux.md)
> **Status:** Implementation-ready
> **Style:** Internal, auth-less (v1), read-optimized. **REST** for lists/ops/mutations + **GraphQL** for graph/entity-detail reads. FastAPI + Pydantic; OpenAPI 3.1 + GraphQL SDL auto-published. All under `/v1`.

---

## 1. Principles

| # | Principle |
|---|---|
| **A1** | **The API is the only boundary the dashboard depends on.** Introducing auth/tenancy later (blueprint §27) is middleware + a `tenant_id` filter, not a redesign. |
| **A2** | **Every claim ships with provenance.** Entity/opportunity responses embed `evidence_refs` and `score.components`. Trust is the product. |
| **A3** | **Cursor pagination everywhere.** Never offset at scale (10M companies). |
| **A4** | **Read-optimized.** Lists/search hit OpenSearch + Redis; detail hits Postgres/AGE. Writes are limited to admin/ops + operator feedback. |
| **A5** | **Versioned + typed.** `/v1` prefix; Pydantic models are the contract; consistent error envelope. |
| **A6** | **GraphQL for graph-shaped reads** (entity pages, neighborhoods) to avoid N+1 and over-fetch; REST for everything else. |

---

## 2. Conventions

### 2.1 Base & versioning
- Base URL: `/v1`. Breaking changes → `/v2`; additive changes stay in `/v1`.
- Content type `application/json`; GraphQL at `/v1/graphql`.

### 2.2 Pagination (cursor)
Request: `?limit=50&cursor=<opaque>`; Response envelope:
```json
{ "data": [ ... ], "page": { "next_cursor": "eyJvIjo0Mn0=", "has_more": true, "limit": 50 } }
```
Cursors encode the sort key + tiebreak id (opaque, base64). No `offset`.

### 2.3 Filtering & sorting
- Filters are explicit query params (`tier`, `industry`, `tech`, `min_score`, `freshness`).
- Sort via `sort=-opportunity_score` (leading `-` = desc). Allowed sort fields are enumerated per endpoint.

### 2.4 Caching
- `ETag` on cacheable GETs; `If-None-Match` → `304`. Entity responses carry the entity `version` (doc 01) in the ETag so a projection change busts caches.
- `Cache-Control: private, max-age=30` on list/search; detail is version-keyed.

### 2.5 Error envelope
```json
{ "error": { "code": "not_found", "message": "opportunity 42 not found",
             "trace_id": "…", "details": {} } }
```
| HTTP | `code` | When |
|---|---|---|
| 400 | `invalid_request` | bad params/body (Pydantic validation detail included) |
| 404 | `not_found` | unknown id |
| 409 | `conflict` | concurrent write / merge conflict |
| 422 | `unprocessable` | semantically invalid (e.g., merge two already-merged) |
| 429 | `rate_limited` | admin bulk ops guard |
| 500 | `internal` | unexpected (trace_id always present) |

### 2.6 Shared object shapes
```jsonc
// EvidenceRef — embedded wherever a claim appears (A2)
{ "id": 8823, "source": "github", "collector": "github_issues",
  "url": "https://…", "snippet": "We're migrating off HubSpot…",
  "claim_type": "signal.pain_mention", "confidence": 0.82, "observed_at": "2026-05-01T…" }

// ScoreVector — embedded on entities/opportunities (A2, doc 05)
{ "opportunity": 0.78, "buying_intent": 0.81, "evidence": 0.66, "freshness": 0.72,
  "relationship": 0.54, "timeline": 0.60, "company_confidence": 0.88, "identity_confidence": 0.71,
  "components": { "…": "…" }, "computed_at": "2026-07-18T…" }
```

---

## 3. REST — Read Endpoints

### 3.1 Opportunities (the dashboard's core)
```
GET /v1/opportunities
  ?tier=gold|silver|bronze|all           (default all)
  &industry=saas&signal_type=funding_raised&tech=hubspot
  &intent_axis=crm&min_score=0.7&freshness=30d
  &sort=-opportunity_score&limit=50&cursor=…
```
`200` →
```json
{ "data": [
    { "id": 42, "tier": "gold", "thesis": "In-market for CRM",
      "company": { "id": 10, "name": "Acme", "domain": "acme.com", "industry": "SaaS" },
      "person": { "id": 91, "name": "Jane Roe", "role": "VP Sales" },
      "department": null, "decision_maker_role": null,
      "primary_signal": { "id": 700, "type": "pain_mention", "intent_axis": "crm",
                          "detected_at": "2026-05-01T…" },
      "scores": { "opportunity": 0.78, "buying_intent": 0.81, "...": "..." },
      "evidence_refs": [ { "id": 8823, "...": "..." } ],
      "updated_at": "2026-07-18T…" }
  ],
  "page": { "next_cursor": "…", "has_more": true, "limit": 50 } }
```
Served from OpenSearch `opportunities` index (facets + sort) with Redis caching (A4).

```
GET /v1/opportunities/{id}          → full card: opportunity + company + person +
                                       all signals + evidence_refs + score.components +
                                       transitions[] (the promotion ledger)
GET /v1/opportunities/{id}/transitions   → Bronze→Silver→Gold ledger
POST /v1/opportunities/{id}/feedback     → { "rating": "good"|"bad", "note": "…" }  (LTR training, doc 05 §9)
```

### 3.2 Companies
```
GET /v1/companies?tech=hubspot&hiring=sdr&industry=saas&freshness=30d&sort=-updated_at&limit=50&cursor=…
GET /v1/companies/{id}                → firmographics + score vector + rollups (top signals/tech/opps)
GET /v1/companies/{id}/timeline?after=2026-01-01     → chronological events (paginated)
GET /v1/companies/{id}/signals?type=hiring&since=90d
GET /v1/companies/{id}/people?role=sales
GET /v1/companies/{id}/opportunities?tier=all
GET /v1/companies/{id}/graph?depth=1..2&edge_types=works_at,uses_tech   → subgraph (doc 02 §10)
GET /v1/companies/{id}/evidence?claim_type=company.domain              → provenance list
```

### 3.3 People
```
GET /v1/people?role=head+of+growth&company=acme.com&limit=50&cursor=…
GET /v1/people/{id}                   → identity + current role + company context + scores + evidence_refs
GET /v1/people/{id}/graph?depth=1
```

### 3.4 Evidence & lineage (provenance, A2)
```
GET /v1/evidence/{id}                 → { url, snippet, claim, confidence, source, collector,
                                          raw_document: { s3_key, fetched_at, http_status } }
GET /v1/lineage/{attribute_ref}       → raw → parsed → evidence → canonical chain for one attribute
                                        (e.g. attribute_ref = "entity:10:current_role")
```
`lineage` powers the "why do we believe this?" UI and satisfies FR-OPS-3.

### 3.5 Search
```
GET /v1/search?q=companies+hiring+SDR+using+HubSpot
  &mode=hybrid|structured|semantic|fulltext    (default hybrid)
  &types=company,person,opportunity
  &filters={"industry":"saas","tier":"gold"}
  &limit=25&cursor=…
```
`200` →
```json
{ "data": [
    { "type": "company", "id": 10, "name": "Acme", "domain": "acme.com",
      "highlight": "…hiring <em>SDR</em>…", "score": 12.4,
      "matched_on": ["hiring_for:sdr","uses_tech:hubspot"],
      "evidence_refs": [ … ] }
  ],
  "interpreted": { "structured_filters": {"hiring":"sdr","tech":"hubspot"}, "free_text": "" },
  "page": { "…": "…" } }
```
Pipeline (blueprint §16.3): intent-parse → BM25 ⊕ kNN → reciprocal-rank fusion → facet filter → rerank by Opportunity Score. `interpreted` echoes how the query was understood (UI shows it, doc 07).

```
GET /v1/search/suggest?q=hub                 → typeahead (tech/company/keyword)
```

---

## 4. REST — Admin / Ops Endpoints

Operator-facing config & control (no auth in v1; network-isolated, A1). All mutations audited (`audit_event`).

### 4.1 Collectors & jobs
```
GET  /v1/admin/collectors                    → list + status + last_run + throughput + error_rate
GET  /v1/admin/collectors/{id}
PATCH /v1/admin/collectors/{id}              → { enabled, cadence_hint }
POST /v1/admin/collectors/{id}/run           → trigger an ad-hoc crawl job → { job_id }
GET  /v1/admin/jobs?status=running|failed|dead&kind=collect&limit=50&cursor=…
GET  /v1/admin/jobs/{id}                      → status, timing, error, trace_id
POST /v1/admin/jobs/{id}/retry               → requeue a failed/dead job
GET  /v1/admin/dlq?stage=parser              → dead-letter inspector
POST /v1/admin/dlq/{id}/replay
```

### 4.2 Keywords / technologies / sources
```
GET/POST/PATCH/DELETE /v1/admin/keywords     → keyword management (term, kind, weight, enabled)
GET/POST/PATCH        /v1/admin/technologies
GET/POST/PATCH        /v1/admin/sources
```

### 4.3 Scoring config
```
GET /v1/admin/scoring/weights                → active scoring_config.weights
PUT /v1/admin/scoring/weights                → replace active weights → enqueues background rescore (doc 05 §6.2)
GET /v1/admin/scoring/history                → prior configs (audit)
```

### 4.4 Entity resolution review queue (doc 04 §11)
```
GET  /v1/admin/resolution/review?limit=25    → borderline pairs w/ features + evidence + side-by-side
POST /v1/admin/resolution/{review_id}/decide → { "decision": "merge"|"no_match" }
POST /v1/admin/entities/{id}/unmerge         → { "split_observation_ids": [...] }   (doc 04 §10)
POST /v1/admin/entities/merge                → { "left": id, "right": id }          (manual merge)
```

### 4.5 Replay / backfill (ops)
```
POST /v1/admin/replay                        → { "from_layer": "parsed", "filter": {...} }  → job_id
GET  /v1/admin/pipeline/lag                  → per-topic consumer lag (blueprint §22)
```

---

## 5. GraphQL — Entity & Graph Reads

Single endpoint `/v1/graphql`. Used by entity detail pages and the graph explorer (avoids N+1, A6). Read-only in v1 (mutations go through REST admin).

### 5.1 Schema (SDL excerpt)
```graphql
scalar DateTime
enum Tier { GOLD SILVER BRONZE UNQUALIFIED ALL }
enum EdgeType { works_at uses_tech hiring_for raised mentions spoke_at competitor_of owns_domain }

type ScoreVector {
  opportunity: Float! buyingIntent: Float! evidence: Float! freshness: Float!
  relationship: Float! timeline: Float! companyConfidence: Float! identityConfidence: Float!
  components: JSON!
}

type EvidenceRef { id: ID! source: String! url: String! snippet: String
                   claimType: String! confidence: Float! observedAt: DateTime! }

type Company {
  id: ID! name: String! domain: String industry: String
  firmographics: JSON!
  scores: ScoreVector!
  opportunities(tier: Tier = ALL): [Opportunity!]!
  timeline(after: DateTime, limit: Int = 50): [TimelineEvent!]!
  signals(type: String, since: DateTime): [Signal!]!
  people(role: String): [Person!]!
  techStack: [Technology!]!
  neighbors(depth: Int = 1, edgeTypes: [EdgeType!]): Subgraph!
  evidence(claimType: String): [EvidenceRef!]!
}

type Person {
  id: ID! name: String! role: String seniority: String
  currentCompany: Company
  scores: ScoreVector!
  authored: [Post!]! spokeAt: [Event!]!
  neighbors(depth: Int = 1): Subgraph!
  evidence: [EvidenceRef!]!
}

type Opportunity {
  id: ID! tier: Tier! thesis: String!
  company: Company! person: Person
  department: String decisionMakerRole: String
  primarySignal: Signal
  scores: ScoreVector!
  transitions: [OpportunityTransition!]!
  evidence: [EvidenceRef!]!
}

type SubgraphNode { id: ID! type: String! label: String! }
type SubgraphEdge { type: EdgeType! from: ID! to: ID! confidence: Float!
                    validFrom: DateTime validTo: DateTime evidence: [EvidenceRef!]! derived: Boolean! }
type Subgraph { nodes: [SubgraphNode!]! edges: [SubgraphEdge!]! }

type Query {
  company(id: ID!): Company
  person(id: ID!): Person
  opportunity(id: ID!): Opportunity
  path(from: ID!, to: ID!, maxHops: Int = 4): Subgraph     # graph explorer
}
```

### 5.2 Example query (entity page in one round-trip)
```graphql
query CompanyPage($id: ID!) {
  company(id: $id) {
    name domain industry
    scores { opportunity buyingIntent components }
    opportunities(tier: ALL) { id tier thesis scores { opportunity } }
    timeline(limit: 20) { eventType occurredAt summary }
    people(role: "sales") { id name role }
    neighbors(depth: 1, edgeTypes: [works_at, uses_tech]) {
      nodes { id type label }
      edges { type from to confidence evidence { url snippet } }
    }
  }
}
```

### 5.3 Resolver notes
- `neighbors`/`path` resolve via AGE openCypher (doc 02 §7); other fields via repositories.
- DataLoader batching per request to collapse N+1 into batched Postgres reads.
- Depth capped server-side (`≤2` for neighbors, `≤4` hops for path) to bound cost.

---

## 6. Non-Functional API Requirements

| Concern | Spec |
|---|---|
| **Latency** | list/search P95 < 400 ms on 10M-company corpus (NFR-6); detail P95 < 250 ms |
| **Throughput** | v1 single operator; design for horizontal scale of stateless API pods |
| **Rate limiting** | admin bulk ops guarded; read endpoints unthrottled internally |
| **Observability** | every request carries/propagates `trace_id`; per-endpoint latency + error metrics |
| **Idempotency** | admin mutations accept `Idempotency-Key` header; safe retries |
| **Schema publishing** | OpenAPI 3.1 at `/v1/openapi.json`; GraphQL SDL at `/v1/graphql/schema` |
| **Backpressure** | expensive search falls back to cached/degraded results rather than timing out |

---

## 7. SaaS Seam (additive, not now)
Per blueprint §27, all additive at the API layer (A1):
- Auth middleware (OIDC) + `tenant_id` extraction → row scoping (Postgres RLS) on **workspace** resources (saved searches, keywords, scoring, feedback). The crawled graph endpoints stay global.
- Usage metering hooks already present (per-endpoint metrics) → billing later.
- No endpoint is redesigned; auth + tenant filter are inserted as middleware.

---

## 8. Open Questions / ADRs
- **ADR-API-1:** GraphQL for reads only vs. also mutations (kept REST for mutations in v1 for simpler auditing).
- **ADR-API-2:** server-driven vs. client-driven search intent parsing (currently server-side `interpreted`).
- **ADR-API-3:** websocket/SSE stream for live job/pipeline status on ops pages.
- **ADR-API-4:** response-shape versioning strategy for embedded `score.components` as the model evolves.
