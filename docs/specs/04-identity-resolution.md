# 04 — Identity Resolution Specification

> **Master spec:** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §11 · DB backing: [`01-database-design.md`](./01-database-design.md) §3.7–3.10
> **Status:** Implementation-ready
> **Why this is the hardest problem:** ER is what makes the data an *asset* rather than a pile of duplicates. **Over-merge silently corrupts the graph** (the highest-weighted risk, blueprint R1); the entire design is defensive around it.

---

## 1. Scope & Principles

Entity Resolution (ER) turns a stream of **observations** (`entity_source` rows, each proving one source's claim about a person or company) into **canonical entities** (`entity` + satellite projection), merging duplicates and choosing attribute values by evidence — without ever destroying an observation.

| Principle | Consequence |
|---|---|
| **P1. Recall then precision** | Cheap blocking finds candidates; expensive scoring decides matches. Never all-pairs (O(n²) is fatal at 100M). |
| **P2. Under-merge ≫ over-merge (in acceptability)** | Duplicates are fixable later; a wrong merge corrupts. Thresholds and clustering bias toward *not* merging when unsure. |
| **P3. Nothing destroyed** | Canonical state is a *projection* over retained observations; recomputable at any past time. |
| **P4. Every merge is auditable & reversible** | `entity_merge` records features+confidence; un-merge is a first-class operation. |
| **P5. Context beats string similarity** | "John Smith" is meaningless without company/handle context; features weight context far above raw name similarity. |
| **P6. Human-in-the-loop for the uncertain band** | `0.60 ≤ p < 0.90` → review queue; operator decisions become training labels. |

---

## 2. The ER Pipeline

```
candidate observation (from extractor)
        │
        ▼
1. NORMALIZE   →  canonical name / domain / role / geo / handle   (deterministic, doc: normalization)
        │
        ▼
2. BLOCK       →  generate blocking keys; fetch candidate cluster from blocking_key  (cheap recall, P1)
        │
        ▼
3. SCORE PAIRS →  feature vector per (candidate, existing) → match probability p     (precision, P5)
        │
        ▼
4. DECIDE      →  p≥0.90 auto-merge · 0.60≤p<0.90 review · p<0.60 no-match  (+ hard rules)
        │
        ▼
5. CLUSTER     →  transitive resolution w/ merge budget + must-not constraints (P2)
        │
        ▼
6. SURVIVE     →  recompute canonical projection from ALL observations (evidence-weighted)
        │
        ▼
7. RECORD      →  entity_merge audit (features, confidence, reversible=true); bump entity.version; audit_event
```

Runs as the `resolver` worker consuming `entities.candidate`, per-entity-anchor ordered (blueprint §14.5) so concurrent observations of the same subject serialize.

---

## 3. Normalization (step 1)

Deterministic canonicalization feeding both blocking and matching.

### 3.1 Company
- Lowercase; strip punctuation; collapse whitespace.
- Remove legal suffixes: `inc, incorporated, llc, ltd, limited, corp, co, gmbh, sa, plc, pvt, pte, bv, ag, oy, ab` (dictionary-driven).
- Map known aliases → keep raw as `entity_alias`.
- Emit `name_core` (suffix-stripped) and `name_soundex`.

### 3.2 Domain
- Public-suffix-list aware reduction to **apex** (`www`, locale, and app subdomains → apex).
- Follow redirects; ignore parked/CDN/placeholder pages; associate MX + tech fingerprint.
- `apex` is the strongest company blocking/matching key.

### 3.3 Person
- Split into given/family with unicode-aware casing; strip honorifics/suffixes.
- Normalize handles (github/twitter/linkedin slug) — **high-value, low-ambiguity** keys.
- Normalize role via a role dictionary → `role_norm`, `seniority`, `department`.

### 3.4 Geo / Role
- Geo → (city, region, country) canonical codes.
- Role → canonical title + seniority band + department (for decision-maker inference, doc 05).

---

## 4. Blocking (step 2 — recall)

Generate multiple **blocking keys** per observation; compare only within shared blocks. Keys stored in `blocking_key(entity_id, key_type, key_value)` and indexed `(key_type, key_value)`.

| Entity | Blocking keys |
|---|---|
| **Company** | `apex_domain`; `name_soundex`; `name_core_first3tokens`; `linkedin_slug`; `homepage_title_hash` |
| **Person** | `email_hash` (if public); `name_core + company_apex`; `name_core + github_handle`; `social_handle`; `name_core + geo` |

- A candidate lands in several blocks; **union** candidate sets, then dedupe via pairwise scoring.
- Block-size guard: if a block is pathologically large (common surname), require a second co-key (name+company) before scoring to avoid quadratic blowups.
- Blocking targets **high recall** (few missed true matches); precision is step 3's job.

---

## 5. Pairwise Matching (step 3 — precision)

For each `(candidate, existing)` pair, compute a feature vector, then a match probability `p = model(features)`.

### 5.1 Company features
| Feature | Type | Signal strength |
|---|---|---|
| `domain_exact` | bool | apex domains equal → decisive |
| `domain_host_variant` | bool | normalized host equal |
| `name_jaro_winkler` | [0,1] | fuzzy name similarity |
| `name_token_jaccard` | [0,1] | token overlap (suffix-stripped) |
| `social_handle_match` | bool | same LinkedIn/Twitter/GitHub org |
| `geo_match` | cat | same HQ city/country |
| `industry_match` | bool | same industry code |
| `homepage_fingerprint` | bool | same favicon/title/logo hash |
| `evidence_cooccurrence` | int | asserted together in same doc |

### 5.2 Person features (context-weighted, P5)
| Feature | Type | Notes |
|---|---|---|
| `email_exact` | bool | decisive (hard rule) |
| `social_handle_match` | bool | very strong, low ambiguity |
| `name_similarity` | [0,1] | **down-weighted alone**; only meaningful with context |
| `same_company_context` | bool | shared company apex — the key disambiguator |
| `role_similarity` | [0,1] | headline/role overlap |
| `doc_cooccurrence` | bool | appear in same evidence document |
| `avatar_hash_match` | bool | same profile image hash |
| `geo_match` | cat | |

### 5.3 Scoring model
- **v1: weighted logistic / rules** — transparent, tunable, needs no training data on day one:
  `p = sigmoid(Σ wᵢ·featureᵢ + b)` with hand-set weights; documented and versioned.
- **v2: trained classifier** (LightGBM/logistic) once the review queue has produced enough operator-labeled match/no-match pairs. Interface unchanged: `score_pair(a, b) -> float`.
- Model version recorded in `entity_merge.method` (`rules:v1`, `model:v3`) for auditability and replay.

### 5.4 Hard rules (override the fuzzy score)
- Company: `domain_exact` → **hard-merge** (p:=1.0) unless a must-not constraint exists.
- Person: `email_exact` or verified `social_handle_match` → hard-merge.
- Must-not: an operator "no_match" decision or a negative label creates a **blocking constraint** that no automatic score can override.

---

## 6. Decision Thresholds (step 4)

| Band | Action |
|---|---|
| `p ≥ 0.90` | **Auto-merge** (or attach to existing canonical) |
| `0.60 ≤ p < 0.90` | **Review queue** (`resolution_review`); operator adjudicates → label |
| `p < 0.60` | **No-match** → new canonical entity |

Thresholds are configurable (in `scoring_config` alongside scoring weights). Conservative by default (P2): raising the auto-merge bar reduces over-merge at the cost of more duplicates/reviews — the acceptable trade.

---

## 7. Clustering (step 5 — transitivity without over-merge)

Pairwise matches form a similarity graph. Naïve transitive closure over-merges (A~B, B~C, A✗C → wrongly one cluster).

- Use **correlation clustering / community detection with a merge budget** and a **must-not constraint set** (from negative labels/operator decisions).
- Prefer **many small correct clusters** over few large wrong ones (P2).
- A candidate merge that would violate a must-not constraint anywhere in the target cluster is **rejected** and routed to review.
- Cluster stability: re-clustering is incremental (only the affected neighborhood recomputes) to bound cost at scale.

---

## 8. Survivorship (step 6 — conflict resolution)

Canonical attribute values are chosen **per field** from all observations by survivorship rules — never last-write-wins.

**Rule order (per attribute):**
1. **Highest aggregate evidence weight** — `Σ source_trust · freshness` across observations asserting the value.
2. **Source trust tier** — `official > verified_api > news > community > inferred` (`source.trust_tier`).
3. **Recency** — tie-breaker for volatile fields (`current_role`, `funding_stage`).
4. **Multiplicity** — a value asserted by N independent sources beats a singleton.

Each canonical field in `entity.attributes` stores:
```json
"current_role": {
  "chosen_value": "VP Sales",
  "chosen_evidence_ids": [8823, 9114],
  "alternatives": [{"value": "Head of Sales", "evidence_ids": [7001], "weight": 0.4}],
  "computed_at": "2026-07-18T..."
}
```
→ conflicts are **visible, explainable, reversible** (surfaced in the UI, doc 07). Survivorship is deterministic, so the projection is fully recomputable from observations (P3, invariant I4).

---

## 9. Historical Tracking & As-Of Queries

- Every observation is timestamped; the canonical projection at any past time is recomputable by replaying survivorship over observations `WHERE observed_at <= :t`.
- Volatile relationships (job changes) are modeled as **temporal edges** (doc 02 §6), not overwrites: leaving a company closes the `works_at` interval; the person's history persists.

---

## 10. Un-Merge (step 7 correction path)

Auto-merge *will* be wrong sometimes; an asset that can't self-correct rots (P4).

**Mechanism:**
1. `entity_merge.reversible=true` + retained `entity_source.entity_id` lineage record which observations came from which pre-merge entity.
2. Un-merge splits the canonical entity by re-pointing the disputed observations to a new/old entity id, adds a **must-not constraint** between the split pair, and re-runs survivorship on both.
3. Edges are re-pointed and re-derived; scores recomputed; everything logged to `audit_event`.
4. Triggerable by operator (from the review UI) or by a detected contradiction (e.g., conflicting verified handles).

---

## 11. Review Queue (human-in-the-loop)

- `resolution_review` holds borderline pairs with `match_prob` + `features`.
- Dashboard page (doc 07) presents side-by-side entities with the deciding features and evidence snippets.
- Operator picks `merge` / `no_match`; the decision:
  - executes the merge/split,
  - writes a **label** (`match`/`no_match` + features) to the training set,
  - creates a must-not constraint on `no_match`.
- Labels feed the v2 model (§5.3) — the queue is both a correctness mechanism and the training-data flywheel.

---

## 12. Quality Metrics & Gates (hooks into doc 09)

| Metric | Definition | Gate |
|---|---|---|
| **Pairwise precision/recall/F1** | on a curated labeled eval set | CI **fails** if F1 drops below baseline |
| **Auto-merge rate** | % candidates auto-merged | monitored; sudden spikes alert |
| **Merge-reversal rate** | un-merges / merges | KPI for over-merge; alert on rise |
| **Review queue depth / latency** | backlog size & age | operational health |
| **Duplicate rate** | est. duplicate canonical entities | sampled audit |
| **Cluster size distribution** | detect runaway supernode merges | alert on outliers |

Over-merge (reversal rate) is watched most closely (P2, R1).

---

## 13. Performance & Scale

- **Blocking indexes** keep candidate sets small; block-size guards prevent quadratic blowups.
- **Incremental resolution:** only the affected neighborhood re-clusters/re-projects per new observation, not the whole graph.
- **Batch backfills** (after a matcher upgrade) run as replay `job`s over `entity_source`, parallelized by blocking partition.
- At 100M people: ER is embarrassingly parallel across disjoint blocks; the shard key (`entity.id`) aligns ER work with future DB shards.

---

## 14. Interfaces (for implementers)

```python
class ResolutionEngine:
    def resolve(self, candidate: CandidateRecord) -> ResolutionResult: ...
    #   -> {entity_id, action: created|attached|merged|review, confidence, features}

class Matcher(Protocol):
    def score_pair(self, a: EntityView, b: EntityView) -> float: ...   # rules v1 -> model v2

class Survivorship:
    def project(self, entity_id: int) -> dict: ...   # recompute canonical attributes from observations
```

---

## 15. Open Questions / ADRs
- **ADR-ER-1:** clustering algorithm choice (correlation clustering vs. constrained connected components) and merge-budget tuning.
- **ADR-ER-2:** when to graduate rules→trained model (label volume threshold).
- **ADR-ER-3:** cross-type resolution (person↔company via `works_at`) feedback into matching.
- **ADR-ER-4:** handling adversarial/spoofed public profiles (fake handles) in person matching.
