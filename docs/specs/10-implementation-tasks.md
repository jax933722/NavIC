# 10 — Implementation Tasks (Epics → Stories → Tasks)

> **Master spec:** all of [`../ARCHITECTURE.md`](../ARCHITECTURE.md) + specs 01–09 · Sequencing: [`08-development-roadmap.md`](./08-development-roadmap.md)
> **Status:** Implementation-ready backlog
> **Format:** Epics (E) → Stories (S) → Tasks (T). Each story has an ID, the milestone it lands in (M0–M6), the workstream (WS-P/C/X/E/O/S from doc 08), dependencies, and **acceptance criteria (AC)**. Estimates are relative points (1/2/3/5/8/13).

**Legend:** `[Mn]` milestone · `[WS-x]` workstream · `⇐` depends on.

---

## E0 — Platform Foundations `[WS-P]`

### S0.1 Monorepo & tooling `[M0]` — 5 pts
- T0.1.1 Init Python workspace (`uv`/poetry), `packages/*` + `apps/*` skeleton per FOLDER_STRUCTURE.
- T0.1.2 TypeScript workspace for `apps/dashboard` (pnpm).
- T0.1.3 Lint/format/type: ruff, mypy, eslint, tsc, pre-commit.
- T0.1.4 CI pipeline skeleton (lint→unit) + PR checks.
- **AC:** `make check` runs lint+type+unit green; empty apps boot.

### S0.2 Core libraries `[M0]` — 8 pts ⇐ S0.1
- T0.2.1 `core/config` (settings, budgets, feature flags).
- T0.2.2 `core/eventbus` interface + **Redis Streams adapter** (+ NATS/Kafka stubs).
- T0.2.3 `core/logging` (structured JSON, mandatory fields) + `core/tracing` (OTel).
- T0.2.4 `core/ids`, `core/errors`, `core/di`.
- **AC:** publish/consume a test event across adapter; logs carry `trace_id`; trace spans exported.

### S0.3 Local infra stack `[M0]` — 5 pts ⇐ S0.1
- T0.3.1 docker-compose: PG16 (+AGE+pgvector), Redis, MinIO, OpenSearch, Temporal.
- T0.3.2 `infra/terraform` skeleton for managed equivalents (staging).
- T0.3.3 Makefile targets: `up`, `down`, `seed`, `migrate`.
- **AC:** `make up` yields a working stack; healthchecks pass.

### S0.4 Schema & migrations `[M0]` — 8 pts ⇐ S0.3
- T0.4.1 Alembic init; translate `schema/schema.sql` → initial migration.
- T0.4.2 Enums, core tables, satellites, evidence/raw partitioned parents.
- T0.4.3 Partition bootstrap + monthly auto-create (maintenance stub).
- T0.4.4 Migration up/down CI test on scratch DB.
- **AC:** migrate up+down clean; partitioned tables created; indexes present.

### S0.5 Storage repositories `[M0]` — 5 pts ⇐ S0.4
- T0.5.1 SQLAlchemy models mirroring schema.
- T0.5.2 Repository per aggregate; **single-writer discipline** enforced.
- T0.5.3 Idempotent upsert helpers (`ON CONFLICT`) + version bump.
- **AC:** integration test writes/reads each aggregate; double-write converges.

### S0.6 Observability baseline `[M0→M6]` — 5 pts
- T0.6.1 Prometheus metrics registry + `/metrics`; Grafana dashboards (ingestion/pipeline/serving).
- T0.6.2 Loki/OpenSearch log sink; trace pipeline into the event envelope.
- T0.6.3 Alert rules (consumer lag, error rate, orphan entities, merge-reversal).
- **AC:** golden-signal dashboards live; a synthetic lag spike alerts.

---

## E1 — Ingestion & Collector Framework `[WS-C]` (spec 03)

### S1.1 Raw store & fetch client `[M0]` — 8 pts ⇐ S0.2
- T1.1.1 `ingestion/raw_store` → S3/MinIO write at `raw/{source}/{yyyy}/{mm}/{hash}` + `raw_document` index.
- T1.1.2 `fetch_client` (httpx, HTTP/2, timeout, retry+backoff+jitter, error taxonomy).
- T1.1.3 `robots.py` (cache + crawl-delay) and `rate_limit.py` (Redis token bucket per host).
- T1.1.4 Content-hash dedupe + conditional GET (ETag/Last-Modified).
- **AC:** fetching a URL persists raw **before** parse; re-fetch unchanged → skipped; robots honored.

### S1.2 Collector contract & runtime `[M0]` — 8 pts ⇐ S1.1
- T1.2.1 `collectors/base` — `BaseCollector` protocol, `Capabilities`, `FetchTask`, `RawResponse`, `CandidateRecord` (evidence mandatory).
- T1.2.2 Collector runtime lifecycle (plan→gate→fetch→persist→emit→checkpoint) with cross-cutting injection.
- T1.2.3 `registry` + decorator + DB-driven enable/cadence.
- T1.2.4 DLQ + poison-message isolation + heartbeats.
- **AC:** a trivial collector runs end-to-end emitting `raw.fetched`; crash mid-run resumes from checkpoint.

### S1.3 First collector: `company_web` `[M0]` — 5 pts ⇐ S1.2
- T1.3.1 plan (homepage→about/team/careers/pricing/changelog), fetch, parse hooks.
- T1.3.2 Golden fixtures + contract/politeness/recovery tests (spec 09 §3.2).
- **AC:** seeded company site produces company/person/job candidates with evidence; golden snapshot locked.

### S1.4 Collector fleet `[M3]` — 13 pts ⇐ S1.2, E3 hardening
- T1.4.1 `rss_blog` · T1.4.2 `news` · T1.4.3 `github` (API-first) · T1.4.4 `hackernews` · T1.4.5 `reddit` · T1.4.6 `producthunt` · T1.4.7 `podcasts`/`conferences` · T1.4.8 `funding`.
- Each: config yaml, contract + golden tests, incremental support.
- **AC:** ≥8 collectors enabled; each passes golden/politeness/incremental tests.

### S1.5 Browser pool `[M3]` — 5 pts
- T1.5.1 Playwright pool (isolated workers, resource caps) using pre-provisioned Chromium.
- T1.5.2 `needs_browser` routing.
- **AC:** a JS-rendered page is fetched via the pool within limits; pool isolated from HTTP workers.

---

## E2 — Extraction & Pipeline `[WS-X]` (spec 03 §3, blueprint §14)

### S2.1 Parsing `[M0]` — 5 pts ⇐ S1.1
- T2.1.1 `parsing/html` (readability, links, structured fields), `json_ld`, `rss`, `pdf`.
- T2.1.2 `ParsedDocument` model; parser worker consuming `raw.fetched` → `documents.parsed`.
- **AC:** raw → ParsedDocument with clean text + links; golden-locked.

### S2.2 Deterministic extraction + evidence `[M0]` — 8 pts ⇐ S2.1
- T2.2.1 Rule extractors (titles/roles, funding phrases, tech dictionary, schema.org).
- T2.2.2 `evidence.py` builder — every claim → Evidence (url, snippet, hash, confidence).
- T2.2.3 Emit `entities.candidate` / `signals.candidate`.
- **AC:** parsed doc → candidates each with mandatory evidence; invariant scan passes.

### S2.3 Normalization `[M1]` — 5 pts ⇐ S2.2
- T2.3.1 company_name/person_name/domain/role/geo/tech normalizers + dictionaries (legal suffixes, PSL, role map, tech aliases).
- T2.3.2 Property-based tests (idempotent, valid apex).
- **AC:** normalizers deterministic & idempotent; feed blocking keys.

### S2.4 LLM extraction path `[M2]` — 8 pts ⇐ S2.2
- T2.4.1 Deterministic prefilter gate (does text plausibly contain entity/signal?).
- T2.4.2 Claude extractor with **schema-constrained** structured output + snippet-as-evidence.
- T2.4.3 Per-day token budget + fallback to deterministic; cost metering.
- T2.4.4 Prompt-injection hardening (treat fetched text as untrusted; never execute).
- **AC:** unstructured text yields structured candidates+evidence; over-budget falls back; cost metered.

### S2.5 Stage framework & replay `[M0→M6]` — 8 pts ⇐ S0.2
- T2.5.1 `pipeline/stage` interface + idempotency keys; `StageContext`.
- T2.5.2 `pipeline/replay` harness (reprocess a layer with filter → job).
- T2.5.3 `pipeline_offset` management for replay control.
- **AC:** replay from Parsed reproduces identical canonical output (determinism test, spec 09 §3.7).

---

## E3 — Entity Resolution & Graph `[WS-E]` (specs 02, 04)

### S3.1 Blocking `[M1]` — 5 pts ⇐ S2.3
- T3.1.1 Blocking-key generation (company + person) → `blocking_key`.
- T3.1.2 Block-size guard (require co-key on huge blocks).
- **AC:** candidate recall via blocking; no all-pairs; large blocks guarded.

### S3.2 Pairwise matching `[M1]` — 8 pts ⇐ S3.1
- T3.2.1 Feature extractors (company + person, context-weighted).
- T3.2.2 `Matcher.score_pair` rules/logistic v1 + hard rules (domain/email exact).
- T3.2.3 Thresholds from `scoring_config`.
- **AC:** pairs scored; ER eval F1 ≥ baseline; over-merge canary = 0.

### S3.3 Clustering & survivorship `[M1]` — 8 pts ⇐ S3.2
- T3.3.1 Constrained clustering w/ merge budget + must-not constraints.
- T3.3.2 Survivorship projection (evidence weight → trust → recency → multiplicity) writing `entity.attributes` with `chosen_evidence_ids` + `alternatives`.
- T3.3.3 `entity_merge` audit + version bump + `audit_event`.
- **AC:** dup crawls → one canonical entity; survivorship correct & explainable.

### S3.4 Review queue & un-merge `[M1/M4]` — 5 pts ⇐ S3.3
- T3.4.1 `resolution_review` population for `0.60≤p<0.90`.
- T3.4.2 Decide endpoint → merge/split + label + must-not constraint.
- T3.4.3 Un-merge (re-point observations, re-derive edges, rescore, audit).
- **AC:** borderline pair adjudicated; wrong merge reversible; label recorded.

### S3.5 Person resolution `[M4]` — 8 pts ⇐ S3.2
- T3.5.1 Context-first person features (company/handle > name).
- T3.5.2 Person satellites + `works_at` with relationship evidence.
- **AC:** people disambiguated by context; person-ER F1 gate green.

### S3.6 Graph builder + AGE `[M2]` — 8 pts ⇐ S3.3
- T3.6.1 `edge` idempotent upsert; confidence noisy-OR; temporal transitions.
- T3.6.2 AGE mirror (outbox) + reconciliation sweep + lag metric.
- T3.6.3 Traversal helpers (neighborhood SQL, motif Cypher).
- T3.6.4 Inference edges (`competitor_of`, inferred `uses_tech`) marked `derived`.
- **AC:** edges written w/ evidence; AGE neighborhood/motif queries return; mirror lag bounded.

---

## E4 — Signals, Opportunities & Scoring `[WS-O]` (spec 05)

### S4.1 Signal classifiers `[M2]` — 8 pts ⇐ S2.2
- T4.1.1 Taxonomy + `signal` writes; classifiers: funding, hiring, tech adoption/churn, pain_mention, product_launch, leadership_change.
- T4.1.2 Strength + intent_axis assignment; evidence linkage.
- **AC:** documents yield classified signals with strength/axis/evidence.

### S4.2 Timeline builder `[M2]` — 3 pts ⇐ S4.1
- T4.2.1 `timeline_event` per company (partitioned); ordering.
- **AC:** company timeline renders chronologically.

### S4.3 Opportunity engine & tiering `[M2]` — 8 pts ⇐ S4.1, S3.6
- T4.3.1 YAML template loader + matcher (signals+graph).
- T4.3.2 `classify()` Gold/Silver/Bronze; opportunity upsert (unique company+template).
- T4.3.3 Promotion/demotion ledger (`opportunity_transition`) + audit.
- T4.3.4 Decision-maker inference (Silver) rules.
- **AC:** ≥2-signal company promotes Bronze→Silver with transition; Silver gets dept/role.

### S4.4 Scoring engine `[M5]` (BI/ES basic in M2) — 8 pts ⇐ S4.3
- T4.4.1 Eight score functions with `components` breakdown.
- T4.4.2 Decay sweep worker + event-driven recompute.
- T4.4.3 Config-driven weights + background rescore on change.
- T4.4.4 Scoring invariant tests (monotonicity/bounds/explainability).
- **AC:** OS ranks opportunities; breakdown visible; weight change rescore works; invariants green.

### S4.5 Gold generation `[M4]` — 5 pts ⇐ S3.5, S4.3
- T4.5.1 Wire person + role + relationship evidence into tiering → Gold.
- **AC:** first Gold opportunities with full relationship evidence.

---

## E5 — Serving: API, Search, Dashboard `[WS-S]` (specs 06, 07)

### S5.1 API skeleton `[M0]` — 5 pts ⇐ S0.5
- T5.1.1 FastAPI app; error envelope; cursor pagination; ETag/version.
- T5.1.2 `/opportunities`, `/companies/{id}`, `/evidence/{id}` (Postgres-backed).
- T5.1.3 OpenAPI publish.
- **AC:** board data served; evidence resolvable.

### S5.2 GraphQL entity/graph reads `[M2/M5]` — 8 pts ⇐ S3.6
- T5.2.1 SDL (Company/Person/Opportunity/Subgraph) + resolvers + DataLoader.
- T5.2.2 `neighbors`/`path` via AGE; depth caps.
- **AC:** entity page in one round-trip; graph queries bounded.

### S5.3 Search `[M5]` — 13 pts ⇐ S4.4
- T5.3.1 OpenSearch mappings (companies/people/opportunities/evidence_text) + `indexer` projector.
- T5.3.2 Hybrid query (BM25 ⊕ kNN + RRF) + rerank by OS; intent parsing (`interpreted`).
- T5.3.3 Facets/aggregations for dashboard; suggest endpoint.
- T5.3.4 Embedding generation (evidence/company/person) into pgvector + OS kNN.
- **AC:** "companies hiring SDR using HubSpot" ranked, evidence-backed, < 400 ms P95.

### S5.4 Admin/ops endpoints `[M3]` — 8 pts ⇐ S1.4
- T5.4.1 Collectors CRUD/run, jobs, DLQ, pipeline lag.
- T5.4.2 Keywords/technologies/sources CRUD.
- T5.4.3 Scoring weights GET/PUT + rescore trigger; resolution review endpoints.
- **AC:** operator can run collectors, inspect jobs/DLQ, tune keywords/scoring, adjudicate ER.

### S5.5 Dashboard — board & detail `[M0→M2]` — 13 pts ⇐ S5.1
- T5.5.1 Component library (TierBadge, ScoreBar+breakdown, EvidenceChip, FreshnessBadge, TimelineView, TransitionLedger, DataTable).
- T5.5.2 Opportunity board (tier filter, facets, URL state, keyboard nav).
- T5.5.3 Opportunity detail (evidence, signals, timeline, transitions, feedback).
- T5.5.4 Company/People detail (tabs, provenance hover).
- **AC:** FR-UI-1/3 met; tier filtering + evidence one click away.

### S5.6 Dashboard — search, graph, ops pages `[M3→M5]` — 13 pts ⇐ S5.2, S5.3, S5.4
- T5.6.1 Search page (modes, interpreted banner, grouped results).
- T5.6.2 Graph explorer (canvas, lazy expand, evidence popovers, temporal slider).
- T5.6.3 Collectors/Jobs/DLQ pages; Review Queue; Keywords; Scoring (live preview); Settings.
- **AC:** FR-UI-2/4/5 met.

### S5.7 Daily digest `[M6]` — 3 pts ⇐ S4.3
- T5.7.1 `digest` worker (new + upgraded from transitions) + in-app bell/view.
- **AC:** daily digest lists new/upgraded opportunities linking into filtered board.

---

## E6 — Scheduler & Orchestration `[WS-C/P]` (blueprint §19)

### S6.1 Temporal scheduling `[M3]` — 8 pts ⇐ S1.2
- T6.1.1 Collect workflow (durable, checkpointed, heartbeat) + activity workers.
- T6.1.2 Per-source cadence + adaptive value×staleness priority from `crawl_state`.
- T6.1.3 Seed-expansion queue with depth/host caps.
- T6.1.4 Backfill/replay workflows.
- **AC:** unattended daily crawl; hot companies re-crawled more; seeds expand safely.

---

## E7 — Scale & Hardening `[WS-P]` (blueprint §26, spec 09)

### S7.1 Partition & retention automation `[M6]` — 5 pts
- T7.1.1 Monthly partition pre-create; cold-tier detach (never drop raw/evidence).
- T7.1.2 Job pruning; score_history retention.
- **AC:** partitions auto-managed; retention = tiering, raw/evidence never deleted.

### S7.2 Replay/backfill ops + DLQ tooling `[M6]` — 5 pts ⇐ S2.5
- **AC:** operator replays a layer; DLQ items inspectable/replayable.

### S7.3 Load testing & SLOs `[M6]` — 5 pts
- T7.3.1 Synthetic corpus; k6 scenarios; 10× scale run.
- **AC:** search/board P95 < 400 ms; pipeline SLOs met; graph latency measured (ADR-KG-1 input).

### S7.4 Data-quality monitors `[M6]` — 5 pts ⇐ S0.6
- **AC:** evidence density, orphan count, merge-reversal, Precision@Gold, lag, freshness all dashboarded + alerting.

---

## E8 — Security, Ethics & Compliance `[WS-P]` (blueprint §25)

### S8.1 Politeness & robots enforcement `[M0/M3]` — 3 pts ⇐ S1.1
- **AC:** robots/rate-limit enforced by runtime; honest UA; public-only.

### S8.2 Suppression / erasure path `[M6]` — 5 pts
- T8.2.1 Subject erasure: tombstone entity + purge raw/evidence + audit.
- **AC:** an erasure request removes a subject and is audited (GDPR-ready).

### S8.3 Secrets & supply chain `[M0→M6]` — 3 pts
- **AC:** secrets in manager (not code/logs); pinned deps + dependency scan; constrained collector egress.

---

## Cross-Reference: Story → Milestone Map

| Milestone | Stories |
|---|---|
| **M0** | S0.1–0.6, S1.1–1.3, S2.1–2.2, S2.5, S5.1, S5.5(start), S8.1, S8.3 |
| **M1** | S2.3, S3.1–3.4, S0.4(partitions), ER F1 gate |
| **M2** | S2.4, S3.6, S4.1–4.3, S4.4(BI/ES basic), S5.2(start), S5.5(finish) |
| **M3** | S1.4–1.5, S5.4, S6.1, S5.6(ops pages) |
| **M4** | S3.5, S4.5, S3.4(un-merge), S5.6(review queue) |
| **M5** | S4.4(full), S5.2(finish), S5.3, S5.6(search/graph/scoring) |
| **M6** | S5.7, S7.1–7.4, S8.2, hardening & gates |

---

## Estimation Summary (relative)

| Epic | Points (approx) |
|---|---|
| E0 Platform | 36 |
| E1 Ingestion/Collectors | 39 |
| E2 Extraction/Pipeline | 34 |
| E3 Entity/Graph | 42 |
| E4 Signals/Opps/Scoring | 32 |
| E5 Serving | 60 |
| E6 Scheduler | 8 |
| E7 Scale/Hardening | 20 |
| E8 Security/Ethics | 11 |
| **Total** | **~282** |

Points are for relative sequencing/capacity planning, not calendar commitments. Critical path (doc 08 §4): E0→E1/E2 spine→E3 ER→E4 tiering→E4.5 Gold→E5 search→E7 hardening.

---

## Definition of Done (applies to every story)
Unit+property tests; golden fixtures for parsers; contract tests for new event schemas; metrics+traces+logs on new workers/endpoints; integration test for DB round-trips; docs/ADRs updated; all CI gates (spec 09 §4) green; feature demoed against its milestone exit gate.
