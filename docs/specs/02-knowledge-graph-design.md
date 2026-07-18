# 02 — Knowledge Graph Design

> **Master spec:** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §10 · DB backing: [`01-database-design.md`](./01-database-design.md) §3.12
> **Status:** Implementation-ready
> **Storage decision:** graph = first-class `edge` rows in PostgreSQL, mirrored into **Apache AGE** (openCypher) in the same database. A dedicated engine (Neo4j/Memgraph) is a *derived, rebuildable index* adopted only if traversal latency demands it — never the source of truth.

---

## 1. Purpose

The knowledge graph is the product's differentiator: it connects people, companies, technologies, signals, and opportunities into a queryable narrative ("person → works_at → company → uses → HubSpot → hiring → RevOps → raised → seed → looking_for → CRM → **opportunity**"). This document specifies the ontology, the physical model, construction rules, temporal semantics, inference, traversal queries, consistency, and the scale plan.

**Why a graph and not just joins:** the operator's core actions — *explore a neighborhood, find paths, match motifs* ("companies using X whose Head of Sales spoke about Y") — are natively graph operations. Relational joins express them awkwardly and re-implement traversal by hand. But at 10B edges we refuse to make an external graph DB the system of record; so we keep edges as transactional rows and expose graph semantics over them.

---

## 2. Ontology

### 2.1 Node types (= `entity.entity_type`)

| Node | Description | Key attributes (in `entity.attributes` / satellite) |
|---|---|---|
| `person` | An individual professional | full_name, current_role, seniority, handles |
| `company` | An organization | primary_domain, industry, employee_range, funding_stage |
| `domain` | A web domain owned by a company | host, apex, mx, tech fingerprint |
| `product` | A product/offering | name, category |
| `technology` | A tool/vendor/stack item | slug, category, aliases |
| `job` | A public job posting | title, department, seniority, location |
| `post` | A blog/news/forum/social item | title, url, author_ref, published_at |
| `event` | Conference/podcast/funding round | kind, name, date |
| `opportunity` | A derived buying opportunity | tier, thesis, score |
| `industry` | Industry taxonomy node | code, name |
| `keyword` | Tracked term/pain point | term, kind |

### 2.2 Edge types (typed · directed · temporal · evidence-backed)

Every edge carries: `confidence ∈ [0,1]`, `evidence_ids BIGINT[]` (non-empty — invariant I2), `valid_from/valid_to`, `first_seen_at/last_seen_at`, `derived BOOL`, and type-specific `attributes JSONB`.

| Edge | From → To | Temporal? | Attributes | Primary source signals |
|---|---|---|---|---|
| `works_at` | person → company | yes | role, seniority, department | team/leadership/about pages, bylines, LinkedIn-style |
| `former_role_at` | person → company | closed interval | role | history, "previously at" |
| `founded` | person → company | point | year | about/press |
| `authored` | person → post | point | — | blog/news byline |
| `spoke_at` | person → event | point | talk_title | conference/podcast pages |
| `uses_tech` | company → technology | yes | source_of_signal | job posts, changelogs, tech fingerprint, case studies |
| `churned_tech` | company → technology | point | replaced_by | "migrated from X", competitor switch |
| `hiring_for` | company → job | interval | department, role | careers pages, job boards |
| `raised` | company → event | point | amount, stage, investors | funding feeds/news |
| `launched` | company → product | point | — | product hunt, changelog, press |
| `mentions` | post/company → keyword/technology/company | point | polarity, context | forums, HN, Reddit, blogs |
| `competitor_of` | company → company | yes | basis | co-mention, "alternative to" |
| `owns_domain` | company → domain | yes | is_primary | DNS/site resolution |
| `has_opportunity` | company → opportunity | interval | tier | opportunity engine |
| `evidences` | evidence → any node | point | claim_type | provenance meta-edge |

**Directionality rule:** edges are stored in their natural direction; the graph adapter exposes both in/out adjacency (indexes on both `src` and `dst`, doc 01 §5). Undirected concepts (`competitor_of`) are stored once and treated symmetrically at query time.

### 2.3 Ontology governance
The node/edge vocabularies are PG enums (`entity_type`, `edge_type`). Adding a type is an **ADR + migration**, deliberately friction-ful so the ontology stays coherent rather than sprawling. New *relationships within existing types* need no schema change (they are `attributes`).

---

## 3. Physical Model

### 3.1 Primary store — the `edge` table
Defined in doc 01 §3.12 / `schema.sql`. Recap of graph-relevant properties:
- Idempotent identity: `UNIQUE(src_entity_id, dst_entity_id, edge_type, valid_from)`.
- Bidirectional indexes + partial index on **current** edges (`WHERE valid_to IS NULL`).
- `evidence_ids[]` non-empty (`CHECK cardinality > 0`).
- `derived` distinguishes observed vs inferred edges.

### 3.2 Graph projection — Apache AGE
A `graph` worker mirrors `entity`→AGE vertices and `edge`→AGE relationships **idempotently and transactionally-eventually** (mirror lag is bounded and monitored). AGE gives openCypher over the same Postgres instance:

```sql
SELECT create_graph('oip');
-- vertices labeled by entity_type, carrying {entity_id, display_name, ...}
-- relationships labeled by edge_type, carrying {edge_id, confidence, valid_to, ...}
```

**Why mirror rather than store only in AGE:** AGE's storage is opaque to our partitioning/retention/ER tooling. Keeping `edge` as plain rows means backups, replay, ER re-pointing, and cold-tiering all work uniformly; AGE is the *query surface*, not the record.

### 3.3 Optional derived engine (scale escape hatch)
If neighborhood/motif latency degrades at billions of edges, stand up Neo4j/Memgraph fed from `edge` via CDC — same pattern as OpenSearch. It is droppable and rebuildable. Decision gate: ADR-KG-1 (see §9).

---

## 4. Graph Construction

The **Graph Builder** (worker role `graph`) consumes canonical entity upserts and classified signals and emits edges. Rules:

1. **Idempotent upsert** on the natural key; on repeat observation, append to `evidence_ids`, bump `last_seen_at`, and re-aggregate `confidence` (§5) — never duplicate.
2. **Evidence-first:** an edge is only written with ≥1 evidence id (I2). Signals and extraction produce the evidence rows first.
3. **Temporal transition:** a new `works_at` for a person at a *different* company closes the prior current `works_at` (`valid_to = detected_at`) and opens a new one — both retained (historical tracking, §6).
4. **Ordering:** per-entity event ordering (partition key = `hash(anchor entity)`, blueprint §14.5) ensures job-change events apply in sequence.
5. **AGE mirror** happens in the same logical unit of work (outbox pattern): edge row committed → mirror event enqueued → AGE upserted; reconciled by a periodic sweep.

### 4.1 Confidence aggregation
```
edge.confidence = 1 − Π_i (1 − confidence_i · freshness_i)      # noisy-OR over evidence
freshness_i     = exp(−age_i / τ_edge_type)
```
Multiple independent evidences raise confidence; stale evidence contributes less. `τ` per edge type (e.g., `works_at` τ≈365d, `hiring_for` τ≈90d).

---

## 5. Inference Edges

Some edges are *derived*, not observed. They are marked `derived=true`, carry the inference method in `attributes.method`, reference the evidences that triggered inference, and are **recomputable** (dropped and regenerated when the method improves).

| Derived edge | Inference rule (v1, transparent) |
|---|---|
| `competitor_of` | co-mention in "alternatives to / vs" contexts above a frequency threshold, or shared category + overlapping keyword mentions |
| `uses_tech` (inferred) | strong tech-name mentions in job posts/changelogs without a direct fingerprint |
| `works_at` (inferred) | author byline on company blog + matching handle, pending stronger evidence |

Inference never *overwrites* observed edges; it adds candidates with lower base confidence, promotable when direct evidence arrives (mirrors the enrich-never-replace ethos).

---

## 6. Temporal Semantics (historical tracking)

- **Point edges** (`raised`, `launched`, `authored`) have `valid_from = valid_to = event date` (or `valid_to NULL` meaning "as of").
- **Interval edges** (`works_at`, `hiring_for`, `uses_tech`) use `valid_from` and open-ended `valid_to NULL` for current, closed when superseded.
- **As-of queries:** "who worked at Acme in March 2026?" →
  ```sql
  SELECT * FROM edge
  WHERE dst_entity_id = :acme AND edge_type = 'works_at'
    AND valid_from <= '2026-03-31' AND (valid_to IS NULL OR valid_to > '2026-03-01');
  ```
- **Never delete on change:** a person leaving a company closes the interval; the edge and its evidence persist, feeding the company's timeline and the person's history.

---

## 7. Traversal Query Catalog

The product needs three traversal classes. Each maps to a concrete implementation.

### 7.1 Neighborhood (entity pages) — always cheap
1–2 hops from a node. Served from `edge` indexes directly (no AGE needed):
```sql
-- People + tech + open opportunities around a company (1 hop, current)
SELECT e.edge_type, e.dst_entity_id, e.attributes, e.confidence
FROM edge e
WHERE e.src_entity_id = :company AND e.valid_to IS NULL
UNION ALL
SELECT e.edge_type, e.src_entity_id, e.attributes, e.confidence
FROM edge e
WHERE e.dst_entity_id = :company AND e.valid_to IS NULL;
```

### 7.2 Motif / path (search + opportunity matching) — AGE openCypher
```cypher
-- "companies using HubSpot whose Head of Sales spoke about outbound"
MATCH (c:company)-[:uses_tech]->(:technology {slug:'hubspot'}),
      (p:person)-[w:works_at]->(c),
      (p)-[:spoke_at]->(ev:event)
WHERE w.attributes.role =~ '(?i).*(head|vp).*sales.*'
  AND ev.attributes.talk_title =~ '(?i).*outbound.*'
  AND w.valid_to IS NULL
RETURN c, p LIMIT 100;
```

### 7.3 Opportunity motifs (engine, doc 05)
Opportunity templates are expressed as graph+signal patterns; the opportunity engine matches them per company. Example thesis "in-market for CRM" = `raised` (recent) ∧ `hiring_for`(sales|revops) ∧ `mentions`(crm|deliverability, negative polarity). The engine compiles each template to a parametric Cypher/SQL matcher.

### 7.4 Path finding (graph explorer)
Shortest/typed paths between two entities for the explorer UI:
```cypher
MATCH p = shortestPath((a)-[*..4]-(b))
WHERE id(a) = :from AND id(b) = :to
RETURN p;
```
Bounded hop count (`*..4`) to keep latency and result size sane.

---

## 8. Consistency, Integrity & Observability

- **Mirror consistency:** the `edge` table is authoritative; AGE is eventually consistent. A reconciliation sweep compares counts/hashes per `(edge_type)` bucket and repairs drift; mirror lag is a monitored metric (alert if > threshold).
- **Referential integrity:** `src/dst` are hard FKs to `entity`. On entity **merge**, edges are re-pointed to the survivor and de-duplicated on the natural key (confidence/evidence merged); on **un-merge**, edges are re-derived from re-pointed observations. All recorded in `audit_event`.
- **Evidence integrity:** `CHECK cardinality(evidence_ids) > 0`; a nightly job verifies each referenced evidence id resolves (soft-FK check, doc 01 §4).
- **Orphan/self-loop guards:** reject `src = dst` except where semantically valid; flag nodes with zero evidence (should not exist).

---

## 9. Scale Plan

At 10M companies / 100M people, edges plausibly reach **1–5B**. Mitigations, applied in order, all additive because edges are plain rows:

1. **Index discipline** — the bidirectional + partial-current indexes keep neighborhood queries O(degree).
2. **Partition `edge`** by `edge_type` then `hash(src_entity_id)` (declarative composite) once the table passes ~a few hundred million rows.
3. **AGE for OLTP neighborhoods only**; push heavy analytical traversals to batch graph compute (GraphFrames/DuckDB over exported edges) or the derived engine.
4. **Derived graph engine** (Neo4j/Memgraph) via CDC if interactive motif latency degrades — **ADR-KG-1** gate: trigger when P95 motif query > 500 ms at production degree distribution.
5. **Degree capping / summarization** for supernodes (e.g., a hugely-mentioned technology) — store aggregate edges + sampled detail to avoid traversal blowups.

**Two invariants that make scale tractable:** (a) edges are rebuildable projections over observations+evidence, so any graph index can be re-created; (b) `entity.id` is the shard key, so `edge` partitions/shards align with entity sharding.

---

## 10. Graph Explorer API surface (for docs 06/07)
- `GET /companies/{id}/graph?depth=1..2&edge_types=…` → subgraph (nodes+edges+confidence+evidence refs).
- `GET /graph/path?from=&to=&max_hops=4` → typed path.
- GraphQL `Company.neighbors(depth, edgeTypes): Subgraph` for entity pages.
Every returned edge includes `evidence_refs` so the UI renders provenance on hover (trust is the product).

---

## 11. Open Questions / ADRs
- **ADR-KG-1:** derived graph engine adoption trigger (P95 motif latency threshold).
- **ADR-KG-2:** supernode strategy (cap vs. summarize vs. tier).
- **ADR-KG-3:** store `competitor_of` symmetric single-row vs. dual-row (query ergonomics vs. write simplicity).
- **ADR-KG-4:** AGE mirror via logical-decoding CDC vs. application outbox (latency vs. operational simplicity).
