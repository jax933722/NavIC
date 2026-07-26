# NavIC — Milestones & 6-Month Roadmap (Detail)

Companion to [`ARCHITECTURE.md`](./ARCHITECTURE.md) §29–§30. Milestones are **thin vertical
slices** — each takes a URL in and produces a scored, evidenced opportunity out. We prove the
spine early and widen it, rather than building horizontal layers that deliver value only at the end.

---

## Milestone exit criteria (the definition of done)

| Milestone | Theme | Hard exit criterion (demoable) |
|---|---|---|
| **M0** | Foundations / spine | A seeded company URL flows Raw→Parsed→Evidence→Entity→Bronze opportunity, visible in the dashboard **with clickable evidence**. |
| **M1** | Evidence & company ER | Two independent crawls of the same company **merge into one canonical entity** with correct survivorship; lineage view shows raw→canonical chain. |
| **M2** | Signals, timeline, tiering | A company with ≥2 signals **promotes Bronze→Silver** and writes an `opportunity_transition`; dashboard filters by Gold/Silver/Bronze/All. |
| **M3** | Collector fleet + scheduler | 6–8 collectors run **unattended daily** via Temporal with retry/checkpoint/rate-limit/robots; new companies discovered without manual seeding. |
| **M4** | People & Gold | First **Gold** opportunities: person + role + company + domain + relationship evidence + signal; ER review queue live. |
| **M5** | Scoring & search | "companies hiring SDR using HubSpot" returns **ranked, evidence-backed** results < 400 ms P95; score breakdown + graph explorer visible. |
| **M6** | Hardening & scale-readiness | Unattended, observable, replayable platform; partitions auto-managed; DLQ ops; daily digest; passes 10× load test and ER F1 gate. |

---

## 6-Month Roadmap

### Month 1 — Spine + Evidence (M0–M1)
**Goal:** prove the medallion spine and the enrich-never-replace invariant.
- Monorepo, `core` interfaces (EventBus, StageContext, repositories, DI), config/budgets.
- Infra: docker-compose + managed Postgres (PITR) + S3 + Redis; Alembic from `schema.sql`.
- Ingestion: raw store (content-hash keyed), fetch client (retry/backoff), robots + rate limit.
- First collector: `company_web` (homepage/about/team/careers).
- Deterministic extraction → **Evidence** → **company** entity; company normalization + resolution + survivorship; alias handling.
- Minimal API (`/opportunities`, `/companies/{id}`, `/evidence/{id}`) + dashboard board of Bronze leads; lineage view.
- **Deliverable:** seeded companies appear as evidenced Bronze leads; re-crawls merge cleanly (no duplicates).

### Month 2 — Signals, Tiers, First Value (M2)
**Goal:** the first genuinely useful version.
- Signal classifiers: funding, hiring, tech adoption/churn, pain-mention; timeline builder.
- Opportunity templates (YAML motifs) + Gold/Silver/Bronze classifier + promotion/demotion ledger.
- Decision-maker inference stub for Silver (dept/role).
- Dashboard: tier filter (Gold/Silver/Bronze/All), company detail + timeline + evidence.
- **Deliverable:** a filterable board of Silver/Bronze opportunities that **upgrade over time**.

### Month 3 — Automated Multi-Source Discovery (M3)
**Goal:** the system feeds itself.
- Collector framework hardening: checkpointing, dead-letter, incremental (ETag/Last-Modified), browser pool.
- Temporal scheduler: per-source cadence + adaptive rate (value × staleness) + controlled seed expansion.
- Live collectors: careers, rss_blog, news, github, hackernews, reddit, producthunt, funding.
- Collectors ops page (status/throughput/errors); jobs + DLQ inspector.
- **Deliverable:** daily unattended discovery of new companies/signals across ≥8 sources.

### Month 4 — People & Gold (M4)
**Goal:** produce the top-tier product output.
- Person extraction + **context-first** person ER (company/handle features weighted above name).
- `works_at` edges with relationship evidence; person detail pages.
- **Gold** generation; ER review queue (operator adjudication → labels feed the matcher).
- Refined Silver decision-maker inference.
- **Deliverable:** first Gold opportunities with full person↔company relationship evidence.

### Month 5 — Scoring, Search, Graph (M5)
**Goal:** ranking, retrieval, and exploration.
- Full multi-score vector (IC/CC/BI/ES/FR/RS/TS/OS) + runtime weights + decay sweep + score-breakdown UI.
- OpenSearch indices (companies/people/opportunities/evidence_text); hybrid BM25+kNN + semantic; faceted dashboard.
- Knowledge-graph explorer over Apache AGE.
- **Deliverable:** structured + natural-language search, ranked and explained; interactive graph.

### Month 6 — Hardening, Scale-Readiness, Digest (M6)
**Goal:** trustworthy, unattended, ready for the next chapter.
- Partition automation, replay/backfill tooling, monitoring/alerting (consumer lag, data-quality, cost).
- Daily digest ("new & upgraded opportunities"); freshness SLA loop tuning.
- Load test at 10× volume; ER F1 CI gate; parser golden snapshots; docs for a second engineer / SaaS seam.
- **Deliverable:** an unattended, observable, replayable Opportunity Intelligence Platform producing a daily flow of Gold/Silver/Bronze.

---

## Sequencing rationale
1. **Spine before breadth** (M0) — one end-to-end slice de-risks the whole architecture before we invest in many collectors.
2. **Evidence & ER before signals** (M1) — signals attached to duplicated/unresolved companies are worthless; get identity right first.
3. **Value by Month 2** — the operator has a useful, self-upgrading board before automation and Gold arrive.
4. **Automation before people** (M3→M4) — feed the graph broadly, then resolve the harder person layer on richer data.
5. **Ranking/search last of the core** (M5) — meaningful ranking needs signals, evidence, and graph to already exist.
6. **Hardening explicitly scheduled** (M6) — not left as "later"; replayability and observability are product features here.

## Post-6-month stretch
- Learned ranker (LambdaMART/GBM) and learned ER classifier from operator labels.
- Kafka/Redpanda backbone; Kubernetes + HPAs on queue lag.
- Derived graph engine (Neo4j/Memgraph) if traversal demands it.
- Multi-tenancy groundwork (§27): `tenant_id` on workspace tables, shared global graph, API-layer auth.
