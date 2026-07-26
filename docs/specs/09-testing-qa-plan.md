# 09 — Testing & QA Plan

> **Master spec:** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §24 · Related: ER ([`04`](./04-identity-resolution.md) §12), Scoring ([`05`](./05-opportunity-scoring-engine.md) §10)
> **Status:** Implementation-ready
> **Thesis:** In a knowledge platform, **the correctness of the *data* is the product**, not just the correctness of the code. So beyond the classic test pyramid we add data-quality layers: golden fixtures, ER evaluation, replay determinism, and scoring invariants — enforced as CI gates.

---

## 1. Quality Objectives

| Objective | Target | Owner test layer |
|---|---|---|
| Code correctness | high unit/integration coverage on logic-heavy packages | unit, integration |
| **Extraction stability** | parser output frozen against golden fixtures | golden fixtures |
| **Identity correctness** | ER F1 ≥ baseline; over-merge (reversal) bounded | ER eval set |
| **Reprocessing safety** | replay is deterministic & idempotent | replay tests |
| **Ranking sanity** | scores monotonic & fully explainable | scoring invariants |
| **Provenance integrity** | 100% of claims have evidence | invariant checks |
| **Performance** | list/search P95 < 400 ms at target volume | load tests |
| **Contract stability** | event/API schemas backward-compatible | contract tests |

---

## 2. The Test Pyramid + Data Layers

```
                 ▲  fewer, slower, higher-confidence
    ┌───────────────────────────┐
    │   E2E (compose+Playwright) │  URL → dashboard shows correct opp w/ evidence
    ├───────────────────────────┤
    │   Load / Perf (k6)         │  throughput + search P95 at 10× volume
    ├───────────────────────────┤
    │   Replay / Determinism     │  reprocess golden raw → identical canonical output
    ├───────────────────────────┤
    │   Integration (testcontainers) │ stage→DB→stage on ephemeral PG/Redis/OpenSearch
    ├───────────────────────────┤
    │   Contract (schema)        │  event envelopes + API/GraphQL + producer/consumer compat
    ├───────────────────────────┤
    │   Data-quality evals       │  ER F1 · scoring invariants · golden fixtures
    ├───────────────────────────┤
    │   Unit + property-based    │  normalizers, matchers, scores, tiering, parsers
    └───────────────────────────┘
                 ▼  many, fast, isolated
```

---

## 3. Layer Specifications

### 3.1 Unit tests
**Targets:** normalizers (company/person/domain/role), `Matcher.score_pair`, survivorship, `classify()` tiering, score functions, template matchers, parsers, decay math.
- **Property-based (Hypothesis)** for normalizers and matchers: e.g., *normalization is idempotent* (`norm(norm(x)) == norm(x)`); *domain reduction always yields a valid apex*; *score functions stay in [0,1]*; *tiering is stable under field reordering*.
- Fast, no I/O; run on every commit.

### 3.2 Golden fixtures (extraction regression lock)
**The most important data-quality test for collectors.** For each collector:
- Freeze representative **raw documents** in `tests/fixtures/collectors/<slug>/`.
- Assert the produced `ParsedDocument` and `CandidateRecord[]` against committed snapshots.
- Any drift fails CI → forces a conscious update (protects against silent parser regressions when a source's HTML shifts, blueprint R2).
- Every `CandidateRecord` in a snapshot must carry evidence (invariant I2 checked here too).

### 3.3 Entity-Resolution evaluation (correctness gate for R1)
- **Curated labeled set** of match / no-match pairs (companies and people) in `tests/data/er/`.
- CI computes **precision / recall / F1**; build **fails** if F1 drops below the locked baseline.
- Separate **over-merge canary set** (known-distinct near-duplicates like "Acme Corp" vs "Acme Software") that must **not** merge — guards the highest risk (over-merge, P2/R1).
- Track auto-merge rate and merge-reversal rate as reported metrics (alerting in prod).

### 3.4 Scoring invariants
- **Monotonicity:** adding a stronger, fresher signal must not decrease BI/OS; decay must not increase FR over time.
- **Explainability completeness:** every `score` row has a non-empty `components` breakdown.
- **Tier-multiplier ordering:** Gold ≥ Silver ≥ Bronze multiplier.
- **Bounds:** all sub-scores ∈ [0,1].
- Run as unit + a small offline eval on sample opportunities.

### 3.5 Contract tests (schema stability)
- **Event envelopes:** JSON-schema for each topic payload; producer/consumer **consumer-driven contract** tests ensure a producer change can't silently break a consumer; schema-version bumps required for breaking changes.
- **API/GraphQL:** OpenAPI + SDL snapshot; breaking-change detection in CI; typed client codegen must compile.

### 3.6 Integration tests (testcontainers)
- Spin ephemeral **Postgres(+AGE+pgvector), Redis, OpenSearch** per test module.
- Verify stage→DB→next-stage: e.g., candidate → resolver → canonical `entity` + `edge`; signal → opportunity → `opportunity_transition`; index projection → OpenSearch query returns it.
- Idempotency: run a stage twice with the same input → single converged row (NFR-3).

### 3.7 Replay / determinism tests
- Take frozen golden **raw** docs → run the full pipeline → assert the **canonical output is deterministic and identical** across runs.
- Reprocess from the Parsed layer after an extractor "change" → verify forward idempotent overwrite (no duplication), proving the replay contract (blueprint §14.1).
- Guards invariant I4 (projections recomputable) — the property the whole enrich-never-replace model depends on.

### 3.8 E2E tests (Playwright)
- **Happy path:** seed a fixture site (local) → run collector → pipeline → dashboard shows the expected Bronze/Silver/Gold opportunity with evidence links resolving.
- **Promotion path:** inject a second signal → assert the row upgrades and a transition appears.
- **Review queue:** borderline pair appears → operator "merge" → entities unify.
- Playwright uses the pre-provisioned Chromium (`/opt/pw-browsers`), never re-downloads.

### 3.9 Load / performance tests (k6 / locust)
- Synthetic corpus at target scale (seed N companies / evidence rows).
- Assert: dashboard & search **P95 < 400 ms** (NFR-6); pipeline sustains ≥100k docs/day (NFR-5), scaling test at 10×.
- Graph neighborhood latency at production-like degree distribution (feeds ADR-KG-1 trigger).

---

## 4. CI/CD Gate Configuration

**Non-negotiable gates (build fails):**
1. Unit + property tests pass.
2. **Parser golden snapshots** unchanged (or consciously updated in the PR).
3. **ER F1 ≥ baseline** and **over-merge canary = 0 merges**.
4. **Event-schema compatibility** (no breaking change without version bump).
5. **Scoring invariants** (monotonicity, bounds, explainability).
6. **"No claim without evidence"** invariant scan (static + integration).
7. **Migrations** apply up *and* down cleanly on a scratch DB.
8. Lint/type-check (ruff/mypy, eslint/tsc).

**Pipeline stages:** `lint/type → unit/property → contract → integration(testcontainers) → replay determinism → e2e (nightly + pre-release) → load (nightly/pre-release)`. Fast gates on every push; heavy gates (e2e/load) nightly and pre-release.

---

## 5. Data-Quality Monitoring (production QA, not just pre-merge)

Testing continues in production because data quality degrades with the live web (blueprint §22):

| Monitor | Signal of a problem |
|---|---|
| Evidence density (avg sources/attribute) | drop → extraction regression |
| Orphan entities (zero evidence) | should be 0; >0 = invariant breach |
| Merge-reversal rate | rising = over-merge creeping in |
| Review-queue depth/age | ER thresholds mis-tuned |
| Extraction yield (entities/doc) per collector | collapse = source changed (golden test should've caught; alert anyway) |
| Precision@Gold (operator ratings) | falling = false-intent (R5) |
| Consumer lag per topic | pipeline health |
| Freshness distribution | stale = crawl cadence issue |

Alerts on these are treated with the same seriousness as infra alerts — **data-quality metrics are production metrics.**

---

## 6. Test Data Management
- **Fixtures** (`tests/fixtures/`) — frozen raw docs + golden snapshots, committed, reviewed on change.
- **Labeled sets** (`tests/data/`) — ER match/no-match pairs, ranking labels, over-merge canaries; grown from the operator review queue over time (the label flywheel, doc 04 §11).
- **Synthetic generators** — for load tests (companies/people/evidence at scale) without hitting real sources.
- **Never test against live sources in CI** — politeness + determinism; use fixtures/mocks.

---

## 7. Definition of Done (per feature)
A feature is done when: unit+property tests written; any parser has golden fixtures; any new event schema has a contract test; any new worker/endpoint emits metrics+traces+logs; integration test covers the DB round-trip; docs/ADRs updated; CI gates green. (Referenced by every milestone in doc 08.)

---

## 8. Open Questions / ADRs
- **ADR-QA-1:** ER F1 baseline value and ratcheting policy (raise the bar as the model improves).
- **ADR-QA-2:** golden-fixture refresh cadence for volatile sources.
- **ADR-QA-3:** synthetic-corpus fidelity for meaningful load numbers.
- **ADR-QA-4:** e2e against a local fixture-site vs. recorded HTTP cassettes (VCR).
