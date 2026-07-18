# NavIC — Engineering Specifications

Detailed, implementation-ready specifications derived from the master blueprint
([`../ARCHITECTURE.md`](../ARCHITECTURE.md)). Each document expands one area of the Software
Architecture Document into a spec a senior engineer can build from directly.

| # | Document | Expands blueprint § | Key backing docs |
|---|---|---|---|
| 01 | [Database Design](./01-database-design.md) | §9 | [`schema.sql`](../schema/schema.sql) |
| 02 | [Knowledge Graph Design](./02-knowledge-graph-design.md) | §10 | 01 |
| 03 | [Collector Framework](./03-collector-framework.md) | §13, §14 | — |
| 04 | [Identity Resolution](./04-identity-resolution.md) | §11 | 01 |
| 05 | [Opportunity & Scoring Engine](./05-opportunity-scoring-engine.md) | §12, §15 | 01, 02 |
| 06 | [Backend API](./06-backend-api.md) | §16, §17 | 01, 05 |
| 07 | [Frontend UI/UX](./07-frontend-uiux.md) | §Frontend, FR-UI-* | 06 |
| 08 | [Development Roadmap](./08-development-roadmap.md) | §29, §30 | all |
| 09 | [Testing & QA Plan](./09-testing-qa-plan.md) | §24 | 04, 05 |
| 10 | [Implementation Tasks](./10-implementation-tasks.md) | all | 08 |

## How these fit together

```
ARCHITECTURE.md  (master spec / SAD — the 30-section blueprint)
   │
   ├── 01 Database ──────────┐
   ├── 02 Knowledge Graph ───┤ data & domain foundations
   ├── 04 Identity Resolution┘
   │
   ├── 03 Collector Framework ┐ how data enters & becomes knowledge
   ├── 05 Opportunity/Scoring ┘
   │
   ├── 06 Backend API ───┐ how knowledge is served
   ├── 07 Frontend UI/UX ┘
   │
   ├── 09 Testing & QA ── quality bar across all of the above
   │
   └── 08 Roadmap → 10 Implementation Tasks  (how & when it gets built)
```

Every spec carries its own **Open Questions / ADRs** section; those are the decisions to
resolve as implementation reaches each area (tracked per milestone in doc 08).
