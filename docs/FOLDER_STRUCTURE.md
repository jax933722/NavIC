# NavIC — Repository Folder Structure

Companion to [`ARCHITECTURE.md`](./ARCHITECTURE.md) §8.

**Principle:** `apps/*` are thin process shells; **all logic lives in `packages/*`** so it is
unit-testable without infrastructure and so services can later be carved out by moving a
package behind its own process (the SaaS seam, §27). Modules never cross-write each other's
tables — they talk through interfaces and the event bus.

```
navic/
├── README.md
├── pyproject.toml / uv.lock            # Python monorepo (workspace)
├── package.json                        # dashboard (pnpm workspace)
├── docker-compose.yml                  # local full stack
│
├── docs/
│   ├── ARCHITECTURE.md                 # the SAD
│   ├── FOLDER_STRUCTURE.md             # this file
│   ├── ROADMAP.md                      # milestones + exit criteria
│   └── schema/
│       └── schema.sql                  # authoritative reference model
│
├── apps/
│   ├── api/                            # FastAPI serving layer (REST + GraphQL)
│   │   ├── main.py                     # app shell only
│   │   ├── rest/                       # routers: opportunities, companies, people, admin
│   │   ├── graphql/                    # schema, resolvers (entity/graph reads)
│   │   ├── deps.py                     # DI wiring (repos, cache, search)
│   │   └── middleware/                 # tracing, error envelope, (future) auth/tenant
│   │
│   ├── worker/                         # ONE worker binary; role via WORKER_ROLE
│   │   ├── main.py                     # dispatch to role handler
│   │   └── roles/                      # collector, parser, extractor, resolver,
│   │                                   #   graph, opportunity, scoring, indexer,
│   │                                   #   digest, maintenance
│   │
│   └── dashboard/                      # Next.js (TypeScript) internal UI
│       ├── app/                        # routes
│       │   ├── dashboard/              # tier-filtered opportunity board (Gold/Silver/Bronze/All)
│       │   ├── companies/
│       │   ├── people/
│       │   ├── opportunities/[id]/     # card + evidence + transitions + timeline
│       │   ├── search/                 # hybrid + semantic
│       │   ├── graph/                  # knowledge-graph explorer
│       │   ├── collectors/             # status, throughput, run
│       │   ├── jobs/                   # jobs + DLQ inspector
│       │   ├── keywords/               # keyword management
│       │   ├── scoring/                # runtime weight tuning
│       │   └── settings/
│       ├── components/                 # EvidenceChip, ScoreBreakdown, TimelineView, GraphCanvas
│       └── lib/api/                    # typed client (OpenAPI/GraphQL codegen)
│
├── packages/                           # THE DOMAIN
│   ├── core/                           # cross-cutting foundations
│   │   ├── config.py                   # settings, feature flags, budgets
│   │   ├── eventbus/                   # EventBus interface + adapters (redis-streams|nats|kafka)
│   │   ├── ids.py, errors.py, logging.py, tracing.py
│   │   └── di.py                       # dependency container
│   │
│   ├── ingestion/
│   │   ├── raw_store.py                # S3 immutable raw persistence (content-hash keyed)
│   │   ├── fetch_client.py             # httpx + retry/backoff/timeout
│   │   ├── browser_pool.py             # Playwright (needs_browser collectors)
│   │   ├── robots.py                   # robots.txt cache + politeness
│   │   └── rate_limit.py               # per-host token buckets (Redis)
│   │
│   ├── collectors/
│   │   ├── base/                       # BaseCollector, lifecycle, mixins, Capabilities
│   │   ├── registry.py                 # plugin discovery (adding a source ≠ core change)
│   │   └── sources/                    # ONE package per source
│   │       ├── company_web/            # homepage/about/team/leadership/careers/pricing/changelog
│   │       ├── rss_blog/
│   │       ├── news/
│   │       ├── github/                 # repos/issues/discussions (API-first)
│   │       ├── reddit/
│   │       ├── hackernews/
│   │       ├── producthunt/
│   │       ├── podcasts/
│   │       ├── conferences/            # speakers/agendas
│   │       └── funding/
│   │
│   ├── parsing/                        # bytes -> ParsedDocument
│   │   ├── html.py, json_ld.py, pdf.py, rss.py, readability.py
│   │   └── models.py                   # ParsedDocument
│   │
│   ├── extraction/
│   │   ├── rules/                      # deterministic extractors (titles, funding, tech dict)
│   │   ├── llm/                        # Claude extractor, prefilter, schema-constrained output, budget
│   │   ├── evidence.py                 # Evidence builder (no claim without evidence)
│   │   └── models.py                   # CandidateRecord
│   │
│   ├── normalization/
│   │   ├── company_name.py, person_name.py, domain.py, role.py, tech.py, geo.py
│   │   └── dictionaries/               # legal suffixes, tech aliases, role maps, public-suffix list
│   │
│   ├── entities/                       # ENTITY RESOLUTION
│   │   ├── models.py
│   │   ├── blocking.py                 # blocking-key generation
│   │   ├── matcher.py                  # pairwise score_pair() (rules -> learned)
│   │   ├── clustering.py               # transitive resolution + merge budget
│   │   ├── survivorship.py             # canonical projection rules
│   │   └── engine.py                   # orchestrates normalize->block->score->cluster->survive->record
│   │
│   ├── graph/
│   │   ├── models.py                   # Edge
│   │   ├── builder.py                  # idempotent edge writes
│   │   ├── age_adapter.py              # mirror to Apache AGE (openCypher)
│   │   └── traversal.py                # neighborhood / motif queries
│   │
│   ├── signals/
│   │   ├── taxonomy.py                 # signal types + intent axes
│   │   └── classifiers/                # funding, hiring, tech_adoption/churn, pain_mention...
│   │
│   ├── opportunities/
│   │   ├── templates/                  # declarative opportunity motifs (YAML)
│   │   ├── engine.py                   # template match -> opportunity
│   │   ├── tiering.py                  # Gold/Silver/Bronze classifier
│   │   ├── promotion.py               # transitions ledger + demotion
│   │   └── decision_maker.py           # Silver dept/role inference
│   │
│   ├── scoring/
│   │   ├── functions.py                # IC, CC, BI, ES, FR, RS, TS, OS
│   │   ├── decay.py                    # nightly decay sweep
│   │   └── config.py                   # runtime weights
│   │
│   ├── search/
│   │   ├── mappings/                   # OpenSearch index mappings
│   │   ├── indexer.py                  # canonical -> index projection
│   │   ├── query.py                    # hybrid BM25 + kNN fusion + rerank
│   │   └── intent.py                   # query understanding (structured vs semantic)
│   │
│   ├── storage/
│   │   ├── models/                     # SQLAlchemy models (mirror schema.sql)
│   │   ├── repositories/               # one repo per aggregate; single-writer discipline
│   │   └── partitions.py               # monthly partition management
│   │
│   └── pipeline/
│       ├── stage.py                    # Stage[TIn,TOut] interface + idempotency
│       ├── context.py                  # StageContext (repos, bus, budgets, trace)
│       └── replay.py                   # layer replay/backfill harness
│
├── infra/
│   ├── terraform/                      # managed PG/S3/OpenSearch/Temporal
│   ├── k8s/                            # Deployments + HPAs (scale-up)
│   └── temporal/                       # workflow/activity definitions, schedules
│
├── migrations/                         # Alembic (source of truth for prod DDL)
│
├── tools/
│   ├── cli/                            # seed, run-collector, replay, rescore, inspect-lineage
│   └── evals/                          # ER F1 eval, ranking eval, scoring invariants
│
└── tests/
    ├── unit/
    ├── integration/                    # testcontainers: PG/Redis/OpenSearch
    ├── e2e/                            # compose + Playwright
    ├── fixtures/                       # frozen raw docs + golden snapshots
    └── data/                           # ER labeled pairs, ranking labels
```
