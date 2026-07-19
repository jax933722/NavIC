# NavIC — Opportunity Intelligence Platform

An internally-operated system that continuously discovers **public buying signals** across the
internet and converts them into ranked, **evidence-backed opportunities** — building and improving
a knowledge graph of people, companies, and their relationships over time.

This is **not** a scraper, an email finder, or an Apollo clone. It is an intelligence platform whose
core invariants are: *everything is an entity with evidence*, *enrich — never replace*, and *every
derived layer is replayable from immutable raw data*.

Opportunities are classified into three continuously-upgraded maturity tiers:

- **Gold** — person + current company + domain + role + relationship evidence + buying signal
- **Silver** — company + domain + buying signal + inferred department + inferred decision-maker role
- **Bronze** — company + domain + weak/early buying signal

## Documentation

The full engineering blueprint lives in [`docs/`](./docs):

| Document | Contents |
|---|---|
| **[docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)** | The Software Architecture Document — all 30 sections (vision → architecture → entity resolution → opportunity engine → scoring → search → scalability → SaaS migration → roadmap). |
| **[docs/schema/schema.sql](./docs/schema/schema.sql)** | Authoritative PostgreSQL reference model (entities, evidence, graph edges, signals, opportunities, scoring, ops). |
| **[docs/FOLDER_STRUCTURE.md](./docs/FOLDER_STRUCTURE.md)** | Full monorepo layout. |
| **[docs/ROADMAP.md](./docs/ROADMAP.md)** | Milestones, exit criteria, and the 6-month roadmap. |
| **[docs/specs/](./docs/specs/)** | Detailed, implementation-ready specifications derived from the blueprint (see below). |

### Detailed specifications ([docs/specs/](./docs/specs/))

Ten implementation-ready specs expanding the blueprint:

1. [Database Design](./docs/specs/01-database-design.md)
2. [Knowledge Graph Design](./docs/specs/02-knowledge-graph-design.md)
3. [Collector Framework](./docs/specs/03-collector-framework.md)
4. [Identity Resolution](./docs/specs/04-identity-resolution.md)
5. [Opportunity & Scoring Engine](./docs/specs/05-opportunity-scoring-engine.md)
6. [Backend API](./docs/specs/06-backend-api.md)
7. [Frontend UI/UX](./docs/specs/07-frontend-uiux.md)
8. [Development Roadmap](./docs/specs/08-development-roadmap.md)
9. [Testing & QA Plan](./docs/specs/09-testing-qa-plan.md)
10. [Implementation Tasks (epics → stories → tasks)](./docs/specs/10-implementation-tasks.md)

> Status: **Baseline v1.0 — implementation-ready blueprint.** Single-operator, single-tenant, no
> auth/billing by design — but built so multi-tenancy is an additive migration, not a rewrite.

## Development

Implementation has begun on **M0 (the spine)** — see [`docs/specs/08-development-roadmap.md`](./docs/specs/08-development-roadmap.md).

```bash
make install     # create venv, install project + dev deps (uv)
make check       # lint (ruff) + tests (pytest)  ← the CI fast gate
make up          # start local infra: Postgres+AGE, Redis, MinIO, OpenSearch
make migrate     # apply Alembic migrations to head

# Run the M0 slice end-to-end (no infra needed — in-memory repos):
.venv/bin/uvicorn apps.api.main:app --port 8000        # the API
python -m tools.cli.seed https://some-company.com      # crawl → pipeline → print opportunities
curl -X POST localhost:8000/v1/admin/seed -d '{"urls":["https://some-company.com"]}' \
     -H 'content-type: application/json'                # or seed via the API
cd apps/dashboard && pnpm install && pnpm dev           # the board at :3000
```

**Monorepo layout** (see [`docs/FOLDER_STRUCTURE.md`](./docs/FOLDER_STRUCTURE.md)): domain logic lives in
`packages/*` (importable, infra-free, unit-testable); `apps/*` are thin process shells.

### M5 — Search · M3 — Pluggable sources · M6 — Digest (complete)

- **Search** (`packages/search`): an intent parser compiles the marquee queries —
  "companies hiring SDR" → `hiring:Sales`, "using HubSpot" → `tech:hubspot`,
  "looking for CRM" → `looking_for:crm`, "people discussing deliverability" → person + axis —
  executed over the repositories with ranked, evidence-backed results and an "interpreted as" echo.
  `GET /v1/search` + a dashboard `/search` page. (OpenSearch is the documented scale path.)
- **Second collector** (`packages/collectors/sources/rss_blog.py`): a structurally different source
  (RSS/Atom feed) added with **only a new module + `@register`** — the framework's core promise,
  proven by a golden-fixture test. Emits company, posts, authors, and signals.
- **Daily digest** (`packages/opportunities/digest.py`): new + upgraded opportunities since a cutoff,
  from the promotion ledger. `GET /v1/digest`.

### M2 + M4 — Signals, Opportunities, and Gold (complete)

- **Signal classifiers** (`packages/signals`): funding, hiring (with department inference), tech
  adoption/churn, pain mentions (mapped to intent axes), product launch — every signal evidence-backed.
- **Multi-template opportunity engine** (`packages/opportunities`): declarative YAML templates,
  Silver decision-maker inference, per-company **timeline**, and a persisted **promotion ledger**
  (Bronze → Silver → Gold transitions).
- **Knowledge-graph edges** (`packages/graph`): typed, evidence-backed `works_at` edges (person → company).
- **Person extraction + resolution** (`packages/extraction`, `packages/entities`): people pulled from
  team/about pages (JSON-LD + text patterns), resolved context-first, linked to their company.
- **Gold generation**: a resolved leadership person connected via a `works_at` edge upgrades a lead to
  Gold (person + role + domain + relationship evidence + signal).
- Verified live end-to-end: three crawled companies produced Gold (with a named decision maker),
  Silver (with an inferred role), and Bronze — visible on the board with evidence.

### M1 — Evidence & Company ER (complete)

- **Entity resolution engine** (`packages/entities`): blocking → weighted-logistic matching (with
  hard rules) → deterministic survivorship → decision (auto-attach / review / create), with
  merge audit and un-merge. Biased against over-merge (the #1 data-quality risk).
- **ER F1 gate** (`tests/eval`): labeled company pairs + over-merge canaries; the build fails if
  F1 < 0.85 or a canary crosses the auto-merge threshold.
- **DB-backed persistence** (`packages/storage/sql_repositories.py`): SQLAlchemy repos implementing
  the same protocols as the in-memory ones; the full pipeline persists to **PostgreSQL 16**,
  verified by integration tests (crawl → resolve → survivorship → Bronze opportunity, re-crawl
  enriches without duplicating). Alembic baseline migration is reversible (up/down/up verified).

```bash
# DB-backed integration tests (skip automatically if no DB is configured):
export NAVIC_DATABASE_URL="postgresql+psycopg://navic@localhost:5432/navic"
make migrate && make test
```

### M0 — the spine (complete)

The full slice runs end-to-end today: **a URL becomes a Bronze opportunity with evidence, visible on the board.**

| Area | Package / app | Status |
|---|---|---|
| Config, IDs, errors, structured logging, event bus (in-memory + interface) | `packages/core` | ✅ tested |
| Deterministic normalization (company name, domain apex, IP-safe) | `packages/normalization` | ✅ property-tested |
| Raw store (immutable, content-addressed) + fetch client (retry/backoff) | `packages/ingestion` | ✅ tested |
| HTML parser → ParsedDocument (title/text/links/meta/JSON-LD) | `packages/parsing` | ✅ tested |
| Collector framework (contract, registry, runtime) + `company_web` collector | `packages/collectors` | ✅ tested |
| Evidence + candidate models (enforces *no claim without evidence*) | `packages/extraction` | ✅ tested |
| Domain-exact resolver (enrich, never replace) | `packages/entities` | ✅ tested |
| Signals → Gold/Silver/Bronze tiering + opportunity engine + 8-score vector | `packages/opportunities`, `packages/scoring` | ✅ tested |
| M0 pipeline: candidates → entities + signals → opportunities | `packages/pipeline` | ✅ e2e tested |
| ORM models + Alembic migration | `packages/storage`, `migrations/` | ✅ import-verified |
| REST API (`/opportunities`, `/companies`, `/evidence`, `/admin/seed`) | `apps/api` | ✅ tested (TestClient + live) |
| Next.js dashboard board (tier filter + evidence chips) | `apps/dashboard` | ✅ builds + typechecks + renders |
| Seed CLI | `tools/cli/seed.py` | ✅ |

`52 unit/integration tests passing`, ruff clean, dashboard `next build` green. Run `make check` to verify.

> The API/pipeline use in-memory repositories in M0 so the whole slice runs without a database.
> The DB-backed adapters (Postgres/MinIO/OpenSearch) implement the same interfaces and land in M1.
