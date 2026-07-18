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

> Status: **Baseline v1.0 — implementation-ready blueprint.** Single-operator, single-tenant, no
> auth/billing by design — but built so multi-tenancy is an additive migration, not a rewrite.
