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
```

**Monorepo layout** (see [`docs/FOLDER_STRUCTURE.md`](./docs/FOLDER_STRUCTURE.md)): domain logic lives in
`packages/*` (importable, infra-free, unit-testable); `apps/*` are thin process shells.

What's built so far (M0, in progress):

| Area | Package | Status |
|---|---|---|
| Config, IDs, errors, structured logging, event bus (in-memory adapter) | `packages/core` | ✅ tested |
| Deterministic normalization (company name, domain apex) | `packages/normalization` | ✅ property-tested |
| Evidence + candidate models (enforces *no claim without evidence*) | `packages/extraction` | ✅ tested |
| Gold/Silver/Bronze tiering gate | `packages/opportunities` | ✅ tested |
| Multi-score vector (buying intent, freshness, evidence, opportunity score) | `packages/scoring` | ✅ tested |
| ORM models + Alembic initial migration | `packages/storage`, `migrations/` | ✅ import-verified |

`43 unit/property tests passing.` Run `make test` to verify.
