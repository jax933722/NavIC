-- =====================================================================
-- Opportunity Intelligence Platform (NavIC) — Canonical Schema (PostgreSQL 16)
-- Companion to docs/ARCHITECTURE.md §9 (Database) and §10 (Knowledge Graph)
--
-- Design invariants encoded here:
--   1. Observation vs Canonical separation (entity_source vs entity).
--   2. Every claim references Evidence (no claim without provenance).
--   3. Append-only where truth accretes; mutable only for projections/scores.
--   4. Time-partition the giants (evidence, raw_document, timeline_event, score_history).
--   5. entity_id is the future shard key; single-writer-per-table.
--
-- This is an implementation sketch, not a migration. Real DDL lives in
-- Alembic migrations; kept here as the authoritative reference model.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- fuzzy name matching / blocking
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector: semantic recall
CREATE EXTENSION IF NOT EXISTS age;          -- Apache AGE: in-DB graph (openCypher)
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- ENUMERATED / REFERENCE TYPES
-- ---------------------------------------------------------------------
CREATE TYPE entity_type   AS ENUM ('person','company','domain','product','technology',
                                   'job','post','event','opportunity','industry','keyword');
CREATE TYPE entity_status AS ENUM ('active','merged','suppressed','tombstoned');
CREATE TYPE opp_tier      AS ENUM ('gold','silver','bronze','unqualified');
CREATE TYPE signal_type   AS ENUM ('funding_raised','hiring','tech_adoption','tech_churn',
                                   'product_launch','pain_mention','leadership_change',
                                   'expansion','partnership','other');
CREATE TYPE edge_type     AS ENUM ('works_at','former_role_at','founded','authored','spoke_at',
                                   'uses_tech','churned_tech','hiring_for','raised','launched',
                                   'mentions','competitor_of','owns_domain','has_opportunity','evidences');
CREATE TYPE source_trust  AS ENUM ('official','verified_api','news','community','inferred');

-- ---------------------------------------------------------------------
-- REFERENCE / CONFIG
-- ---------------------------------------------------------------------
CREATE TABLE source (
    id            BIGSERIAL PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,           -- 'github','reddit','company_web'...
    display_name  TEXT NOT NULL,
    trust_tier    source_trust NOT NULL DEFAULT 'community',
    base_url      TEXT,
    config        JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE collector (
    id            BIGSERIAL PRIMARY KEY,
    source_id     BIGINT NOT NULL REFERENCES source(id),
    slug          TEXT UNIQUE NOT NULL,           -- 'github_issues','careers_page'...
    version       TEXT NOT NULL,
    capabilities  JSONB NOT NULL DEFAULT '{}',    -- {supports_incremental, needs_browser,...}
    cadence_hint  INTERVAL,
    enabled       BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE industry  (id BIGSERIAL PRIMARY KEY, code TEXT UNIQUE, name TEXT NOT NULL);
CREATE TABLE category  (id BIGSERIAL PRIMARY KEY, slug TEXT UNIQUE, name TEXT NOT NULL);
CREATE TABLE keyword   (id BIGSERIAL PRIMARY KEY, term TEXT UNIQUE NOT NULL,
                        kind TEXT, weight REAL DEFAULT 1.0, enabled BOOLEAN DEFAULT true);
CREATE TABLE technology (id BIGSERIAL PRIMARY KEY, slug TEXT UNIQUE, name TEXT NOT NULL,
                         category TEXT, aliases TEXT[] DEFAULT '{}');

CREATE TABLE scoring_config (
    id          BIGSERIAL PRIMARY KEY,
    active      BOOLEAN NOT NULL DEFAULT false,   -- exactly one active row
    weights     JSONB NOT NULL,                   -- {w1..w7, decay_tau{...}, thresholds{...}}
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- RAW LAYER  (index over immutable S3 bytes) — PARTITIONED BY MONTH
-- ---------------------------------------------------------------------
CREATE TABLE raw_document (
    id            BIGSERIAL,
    source_id     BIGINT NOT NULL REFERENCES source(id),
    collector_id  BIGINT NOT NULL REFERENCES collector(id),
    url           TEXT NOT NULL,
    s3_key        TEXT NOT NULL,                  -- bytes live in object store
    content_hash  BYTEA NOT NULL,                 -- sha256(body); dedupe + idempotency
    content_type  TEXT,
    http_status   INT,
    headers       JSONB,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, fetched_at)
) PARTITION BY RANGE (fetched_at);
CREATE INDEX raw_document_hash_idx ON raw_document (content_hash);
CREATE INDEX raw_document_url_idx  ON raw_document (url, fetched_at DESC);
-- + monthly partitions raw_document_YYYY_MM created by maintenance worker.

-- ---------------------------------------------------------------------
-- EVIDENCE  (the most important table) — PARTITIONED BY MONTH
-- Every canonical claim / edge references evidence.
-- ---------------------------------------------------------------------
CREATE TABLE evidence (
    id              BIGSERIAL,
    source_id       BIGINT NOT NULL REFERENCES source(id),
    collector_id    BIGINT NOT NULL REFERENCES collector(id),
    raw_document_id BIGINT,                        -- link back to raw (soft; partitioned)
    url             TEXT NOT NULL,
    content_hash    BYTEA NOT NULL,
    claim_type      TEXT NOT NULL,                 -- 'person.role','company.domain','signal.funding'
    claim           JSONB NOT NULL,                -- structured claim payload
    snippet         TEXT,                          -- human-readable proof excerpt
    confidence      REAL NOT NULL DEFAULT 0.5,     -- [0,1]
    embedding       vector(1024),                  -- semantic recall (nullable)
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, observed_at)
) PARTITION BY RANGE (observed_at);
CREATE INDEX evidence_claim_idx   ON evidence (claim_type, observed_at DESC);
CREATE INDEX evidence_hash_idx    ON evidence (content_hash);
CREATE INDEX evidence_claim_gin   ON evidence USING GIN (claim);
-- HNSW vector index created per-partition or on a rollup table:
--   CREATE INDEX ON evidence USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------
-- ENTITY CORE  (canonical projection)
-- ---------------------------------------------------------------------
CREATE TABLE entity (
    id            BIGSERIAL PRIMARY KEY,           -- future shard key: hash(id)
    entity_type   entity_type NOT NULL,
    canonical_key TEXT,                            -- domain apex / resolved handle
    display_name  TEXT,
    attributes    JSONB NOT NULL DEFAULT '{}',     -- survivorship projection incl. chosen_evidence_ids
    status        entity_status NOT NULL DEFAULT 'active',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    version       BIGINT NOT NULL DEFAULT 1,       -- bumped on upsert; cache/index invalidation
    UNIQUE (entity_type, canonical_key)
);
CREATE INDEX entity_name_trgm ON entity USING GIN (display_name gin_trgm_ops);
CREATE INDEX entity_attrs_gin ON entity USING GIN (attributes);
CREATE INDEX entity_type_idx  ON entity (entity_type, status);

-- Append-only observations feeding a canonical entity.
CREATE TABLE entity_source (
    id             BIGSERIAL PRIMARY KEY,
    entity_id      BIGINT NOT NULL REFERENCES entity(id),
    source_id      BIGINT NOT NULL REFERENCES source(id),
    collector_id   BIGINT NOT NULL REFERENCES collector(id),
    external_id    TEXT,                           -- id within the source
    raw_attributes JSONB NOT NULL,                 -- as-observed, pre-survivorship
    evidence_id    BIGINT NOT NULL,                -- provenance (partitioned table; soft ref)
    match_prob     REAL,                           -- prob this obs belongs to entity_id
    observed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX entity_source_entity_idx ON entity_source (entity_id, observed_at DESC);
CREATE INDEX entity_source_ext_idx    ON entity_source (source_id, external_id);

-- Merge/unmerge audit ledger (reversible).
CREATE TABLE entity_merge (
    id                  BIGSERIAL PRIMARY KEY,
    surviving_entity_id BIGINT NOT NULL REFERENCES entity(id),
    merged_entity_id    BIGINT NOT NULL,           -- kept for un-merge lineage
    method              TEXT NOT NULL,             -- 'domain_exact','model:v3','manual'
    confidence          REAL NOT NULL,
    features            JSONB NOT NULL,            -- the pair feature vector
    reversible          BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX entity_merge_surv_idx ON entity_merge (surviving_entity_id);

CREATE TABLE entity_alias (
    id          BIGSERIAL PRIMARY KEY,
    entity_id   BIGINT NOT NULL REFERENCES entity(id),
    alias       TEXT NOT NULL,
    alias_type  TEXT,                              -- 'legal','dba','handle','misspelling'
    confidence  REAL DEFAULT 0.7,
    UNIQUE (entity_id, alias)
);
CREATE INDEX entity_alias_trgm ON entity_alias USING GIN (alias gin_trgm_ops);

-- Blocking keys for entity resolution recall (see §11.2).
CREATE TABLE blocking_key (
    entity_id  BIGINT NOT NULL REFERENCES entity(id),
    key_type   TEXT NOT NULL,                      -- 'apex_domain','name_soundex','handle'...
    key_value  TEXT NOT NULL,
    PRIMARY KEY (entity_id, key_type, key_value)
);
CREATE INDEX blocking_key_lookup ON blocking_key (key_type, key_value);

-- Human adjudication queue for borderline matches (0.60 <= p < 0.90).
CREATE TABLE resolution_review (
    id            BIGSERIAL PRIMARY KEY,
    left_entity   BIGINT NOT NULL REFERENCES entity(id),
    right_entity  BIGINT NOT NULL REFERENCES entity(id),
    match_prob    REAL NOT NULL,
    features      JSONB NOT NULL,
    decision      TEXT,                            -- NULL | 'merge' | 'no_match'
    decided_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- TYPED SATELLITES (hot, queryable fields; PK = entity.id)
-- ---------------------------------------------------------------------
CREATE TABLE company (
    entity_id       BIGINT PRIMARY KEY REFERENCES entity(id),
    primary_domain  TEXT,
    legal_name      TEXT,
    industry_id     BIGINT REFERENCES industry(id),
    employee_range  TEXT,
    hq_country      TEXT,
    hq_city         TEXT,
    founded_year    INT,
    funding_stage   TEXT,
    linkedin_url    TEXT,
    tech_stack      JSONB DEFAULT '[]',
    intent_vector   vector(1024)
);
CREATE UNIQUE INDEX company_domain_uidx ON company (primary_domain) WHERE primary_domain IS NOT NULL;

CREATE TABLE person (
    entity_id          BIGINT PRIMARY KEY REFERENCES entity(id),
    full_name          TEXT,
    first_name         TEXT,
    last_name          TEXT,
    current_company_id BIGINT REFERENCES entity(id),
    current_role       TEXT,
    seniority          TEXT,
    headline           TEXT,
    github_handle      TEXT,
    linkedin_url       TEXT,
    bio_vector         vector(1024)
);
CREATE INDEX person_company_idx ON person (current_company_id);
CREATE INDEX person_name_trgm   ON person USING GIN (full_name gin_trgm_ops);

CREATE TABLE domain (
    id          BIGSERIAL PRIMARY KEY,
    entity_id   BIGINT REFERENCES entity(id),     -- owning company
    host        TEXT NOT NULL,
    apex        TEXT NOT NULL,
    is_primary  BOOLEAN DEFAULT false,
    mx          TEXT[],
    tech_stack  JSONB DEFAULT '[]',
    resolved_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (host)
);
CREATE INDEX domain_apex_idx ON domain (apex);

-- ---------------------------------------------------------------------
-- KNOWLEDGE GRAPH — typed, temporal, evidence-backed edges
-- (also projected into AGE graph 'oip' for openCypher traversal)
-- ---------------------------------------------------------------------
CREATE TABLE edge (
    id             BIGSERIAL PRIMARY KEY,
    src_entity_id  BIGINT NOT NULL REFERENCES entity(id),
    dst_entity_id  BIGINT NOT NULL REFERENCES entity(id),
    edge_type      edge_type NOT NULL,
    attributes     JSONB NOT NULL DEFAULT '{}',    -- role, amount, stage...
    confidence     REAL NOT NULL DEFAULT 0.5,
    evidence_ids   BIGINT[] NOT NULL DEFAULT '{}',
    derived        BOOLEAN NOT NULL DEFAULT false, -- inferred vs observed
    valid_from     TIMESTAMPTZ,
    valid_to       TIMESTAMPTZ,                    -- NULL = current
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (src_entity_id, dst_entity_id, edge_type, valid_from)
);
CREATE INDEX edge_src_idx ON edge (src_entity_id, edge_type);
CREATE INDEX edge_dst_idx ON edge (dst_entity_id, edge_type);
CREATE INDEX edge_current_idx ON edge (edge_type) WHERE valid_to IS NULL;

-- ---------------------------------------------------------------------
-- SIGNALS · TIMELINE · OPPORTUNITIES
-- ---------------------------------------------------------------------
CREATE TABLE signal (
    id                BIGSERIAL PRIMARY KEY,
    company_entity_id BIGINT NOT NULL REFERENCES entity(id),
    person_entity_id  BIGINT REFERENCES entity(id),
    signal_type       signal_type NOT NULL,
    strength          REAL NOT NULL DEFAULT 0.5,   -- [0,1] raw
    intent_axis       TEXT,                        -- 'crm','deliverability','analytics'...
    decayed_score     REAL,                        -- recomputed by decay sweep
    evidence_ids      BIGINT[] NOT NULL DEFAULT '{}',
    attributes        JSONB NOT NULL DEFAULT '{}',
    detected_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX signal_company_idx ON signal (company_entity_id, signal_type, detected_at DESC);
CREATE INDEX signal_axis_idx    ON signal (intent_axis, detected_at DESC);

CREATE TABLE timeline_event (
    id                BIGSERIAL,
    company_entity_id BIGINT NOT NULL,
    event_type        TEXT NOT NULL,
    signal_id         BIGINT,
    summary           TEXT,
    evidence_ids      BIGINT[] NOT NULL DEFAULT '{}',
    occurred_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);
CREATE INDEX timeline_company_idx ON timeline_event (company_entity_id, occurred_at DESC);

CREATE TABLE opportunity (
    id                   BIGSERIAL PRIMARY KEY,
    company_entity_id    BIGINT NOT NULL REFERENCES entity(id),
    person_entity_id     BIGINT REFERENCES entity(id),
    tier                 opp_tier NOT NULL DEFAULT 'bronze',
    template_id          TEXT,                     -- which opportunity template matched
    thesis               TEXT,
    department           TEXT,                     -- Silver: suggested department
    decision_maker_role  TEXT,                     -- Silver: suggested role
    primary_signal_id    BIGINT REFERENCES signal(id),
    opportunity_score    REAL NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'open',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_entity_id, template_id)
);
CREATE INDEX opportunity_tier_score_idx ON opportunity (tier, opportunity_score DESC);
CREATE INDEX opportunity_company_idx    ON opportunity (company_entity_id);

-- Promotion/demotion ledger (Bronze -> Silver -> Gold and back).
CREATE TABLE opportunity_transition (
    id             BIGSERIAL PRIMARY KEY,
    opportunity_id BIGINT NOT NULL REFERENCES opportunity(id),
    from_tier      opp_tier,
    to_tier        opp_tier NOT NULL,
    reason         TEXT,
    score_delta    REAL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX opp_transition_idx ON opportunity_transition (opportunity_id, created_at DESC);

-- ---------------------------------------------------------------------
-- SCORING  (latest per subject+type; history partitioned)
-- ---------------------------------------------------------------------
CREATE TABLE score (
    subject_kind  TEXT NOT NULL,                   -- 'entity' | 'opportunity'
    subject_id    BIGINT NOT NULL,
    score_type    TEXT NOT NULL,                   -- 'identity','company','buying_intent',
                                                   -- 'evidence','freshness','relationship',
                                                   -- 'timeline','opportunity'
    value         REAL NOT NULL,
    components    JSONB NOT NULL,                  -- explainability breakdown
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subject_kind, subject_id, score_type)
);

CREATE TABLE score_history (
    subject_kind  TEXT NOT NULL,
    subject_id    BIGINT NOT NULL,
    score_type    TEXT NOT NULL,
    value         REAL NOT NULL,
    components    JSONB NOT NULL,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subject_kind, subject_id, score_type, computed_at)
) PARTITION BY RANGE (computed_at);

-- ---------------------------------------------------------------------
-- OPERATIONS  (crawl state, jobs, pipeline offsets)
-- ---------------------------------------------------------------------
CREATE TABLE crawl_state (
    collector_id   BIGINT NOT NULL REFERENCES collector(id),
    seed_key       TEXT NOT NULL,                  -- host / seed url / cursor scope
    cursor         JSONB,                          -- checkpoint for resume
    etag           TEXT,
    last_modified  TEXT,
    last_crawled   TIMESTAMPTZ,
    next_due       TIMESTAMPTZ,
    value_score    REAL DEFAULT 0,                 -- for value*staleness priority
    PRIMARY KEY (collector_id, seed_key)
);
CREATE INDEX crawl_state_due_idx ON crawl_state (next_due);

CREATE TABLE job (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL,                    -- 'collect','replay','backfill','rescore'
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|running|succeeded|failed|dead
    collector_id BIGINT REFERENCES collector(id),
    payload      JSONB,
    error        TEXT,
    trace_id     TEXT,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX job_status_idx ON job (status, created_at DESC);

CREATE TABLE pipeline_offset (
    consumer_group TEXT NOT NULL,
    topic          TEXT NOT NULL,
    partition      INT NOT NULL,
    committed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    offset_value   BIGINT NOT NULL,
    PRIMARY KEY (consumer_group, topic, partition)
);

-- ---------------------------------------------------------------------
-- AUDIT LEDGER (never expired — part of the asset)
-- ---------------------------------------------------------------------
CREATE TABLE audit_event (
    id          BIGSERIAL PRIMARY KEY,
    actor       TEXT NOT NULL DEFAULT 'system',    -- 'system' | 'operator'
    action      TEXT NOT NULL,                     -- 'merge','unmerge','tier_change','config_change','erasure'
    subject     TEXT NOT NULL,
    detail      JSONB NOT NULL,
    trace_id    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX audit_action_idx ON audit_event (action, created_at DESC);

-- ---------------------------------------------------------------------
-- AGE GRAPH bootstrap (derived-in-DB graph over the same entities/edges)
-- ---------------------------------------------------------------------
-- SELECT create_graph('oip');
-- Nodes labeled by entity_type; relationships labeled by edge_type.
-- The graph worker mirrors `entity`/`edge` writes into AGE idempotently.
-- =====================================================================
