# 07 — Frontend UI/UX Specification

> **Master spec:** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §FRONTEND + FR-UI-* · Data source: [`06-backend-api.md`](./06-backend-api.md)
> **Status:** Implementation-ready
> **Stack:** Next.js (App Router) + TypeScript + React, server components for data fetching, TanStack Query for client cache, Tailwind + a small component library. Internal tool for **one operator** — optimize for information density, provenance, and speed, not marketing polish.

---

## 1. UX Principles

| # | Principle | Manifestation |
|---|---|---|
| **U1** | **Evidence is one click away, always.** Every claim, score, and edge exposes its provenance. | `EvidenceChip` everywhere; "why?" affordance on scores; lineage drawer. |
| **U2** | **Tier is the primary lens.** Gold/Silver/Bronze/All is the master filter. | Persistent tier segmented control on the board. |
| **U3** | **The narrative matters.** Show the *timeline* and the *promotion arc*, not just a row. | Timeline view + transition ledger on every opportunity. |
| **U4** | **Density over decoration.** The operator scans hundreds of leads. | Compact tables, sticky filters, keyboard nav. |
| **U5** | **Explain the score.** No opaque numbers. | Score breakdown popover with sub-scores + inputs (doc 05). |
| **U6** | **Operator controls the machine.** Keywords, sources, scoring, review queue are first-class pages. | Full admin surface (FR-UI-5). |
| **U7** | **Freshness is visible.** Stale intent is worthless; show age prominently. | Relative timestamps + freshness badges + decay indicators. |

---

## 2. Information Architecture / Navigation

```
Top-level nav (persistent left rail):
  ● Dashboard            (opportunity board — default landing)
  ● Companies
  ● People
  ● Opportunities        (saved views / all)
  ● Search
  ● Graph Explorer
  ─────────────────────
  Operator:
  ● Collectors
  ● Jobs                 (+ DLQ)
  ● Review Queue         (entity resolution)
  ● Keywords
  ● Scoring
  ● Settings
```

Global elements: command palette (⌘K) for jump-to-entity/search; global search bar in header; freshness/last-crawl indicator; daily-digest bell.

---

## 3. Page Specifications

For each page: purpose, data source (doc 06 endpoint), layout, key components, states (loading/empty/error), and interactions.

### 3.1 Dashboard — Opportunity Board `/dashboard`
**Purpose:** the operator's home; the ranked, filterable stream of opportunities. Satisfies FR-UI-1.
**Data:** `GET /v1/opportunities?tier=&filters&sort=-opportunity_score` (cursor-paginated).

**Layout:**
```
┌───────────────────────────────────────────────────────────────────────────┐
│  [ Gold | Silver | Bronze | All ]  ← tier segmented control (U2)   ⟳ fresh  │
│  Filters: Industry ▾  Signal ▾  Technology ▾  Intent axis ▾  Freshness ▾    │
│           Score range ▷────────◁          [ Saved views ▾ ]  [ Export ]     │
├───────────────────────────────────────────────────────────────────────────┤
│  OPPORTUNITY            COMPANY        SIGNAL           SCORE   FRESH  TIER  │
│ ─────────────────────────────────────────────────────────────────────────  │
│  In-market for CRM      Acme ·acme.com pain: CRM 🔥    0.78▮▮  3d    ●Gold  │
│    Jane Roe · VP Sales        [evidence ▸]  ▸ expand                        │
│  Deliverability pain    Globex        pain: bounce     0.64▮   9d    ●Silv  │
│    → Head of Growth (suggested)                                             │
│  …                                                                          │
│                                            [ load more ]                     │
└───────────────────────────────────────────────────────────────────────────┘
```

**Components:** `TierFilter`, `FacetBar`, `OpportunityRow` (expandable), `ScoreBar` (with breakdown popover, U5), `FreshnessBadge` (U7), `EvidenceChip`.
**Row expand:** reveals top evidence snippets, all signals, suggested decision-maker (Silver), and a "View opportunity" link.
**States:** skeleton rows (loading); "No opportunities match — widen filters" (empty); inline retry (error).
**Interactions:** tier switch (instant, cached), facet multi-select, sort, saved views, keyboard j/k to move rows, `o` to open. Filters persist in URL (shareable, back-button friendly).

### 3.2 Opportunity Detail `/opportunities/[id]`
**Purpose:** the full case for a lead. Satisfies FR-UI-3.
**Data:** `GET /v1/opportunities/{id}` + `/transitions`.

**Layout (three regions):**
- **Header:** tier badge, thesis, company + person, Opportunity Score with **breakdown popover** (all 8 sub-scores, U5), freshness, feedback thumbs (`good`/`bad` → `POST /feedback`, doc 05 §9).
- **Left column — Evidence & Signals:** grouped `EvidenceChip` list (each: source icon, snippet, URL, date, confidence); signals with strength + intent axis.
- **Right column — Narrative:** **Timeline** (U3) of the company's events; **Promotion ledger** (transitions Bronze→Silver→Gold with reasons + score deltas); suggested decision-maker (Silver) or resolved person + relationship evidence (Gold).

**Interactions:** click evidence → opens source in new tab + lineage drawer; click person/company → entity page; "Explore in graph" → graph explorer centered here.

### 3.3 Companies `/companies` and `/companies/[id]`
**List:** filter by tech/hiring/industry/freshness (`GET /v1/companies?...`); columns: name, domain, industry, top signal, #opportunities, CC score, updated.
**Detail:** GraphQL `CompanyPage` query (one round-trip, doc 06 §5.2):
- Firmographics card (with per-field provenance on hover — survivorship `alternatives` shown, doc 04 §8).
- Score vector card.
- Tabs: **Opportunities** · **Timeline** · **Signals** · **People** · **Tech Stack** · **Graph** · **Evidence**.
- People tab lists resolved people with `works_at` role + relationship-evidence chip.

### 3.4 People `/people` and `/people/[id]`
**List:** filter by role/company. **Detail:** identity (with alternatives/aliases), current company + role (relationship evidence), authored posts, spoke-at events, 1-hop graph, IC score with breakdown. Conflicting attributes surface the survivorship `alternatives` (U1).

### 3.5 Search `/search`
**Purpose:** structured + full-text + semantic (FR-UI-2). **Data:** `GET /v1/search`.
- Big query box with mode toggle (Hybrid/Structured/Semantic/Full-text) and typeahead (`/search/suggest`).
- **"Interpreted as"** banner echoes `interpreted.structured_filters` + free text (transparency — the operator sees how "companies hiring SDR using HubSpot" was parsed).
- Result cards grouped by type (Company/Person/Opportunity), each with highlight snippet, `matched_on` chips, evidence, and a score.
- Example prompts shown when empty: "companies hiring SDR", "companies using HubSpot", "people discussing deliverability", "companies looking for CRM".

### 3.6 Graph Explorer `/graph`
**Purpose:** interactive knowledge-graph navigation (FR-UI-4). **Data:** GraphQL `neighbors`/`path`.
- Canvas (Cytoscape.js or react-force-graph) rendering nodes (typed color/shape) + edges (typed, labeled, confidence-weighted thickness).
- Center on an entity; expand neighbors on click (lazy, depth-limited); filter by edge type; toggle **derived** edges (dashed, doc 02 §5).
- Edge hover → `EvidenceChip` popover (provenance, U1); temporal slider to view the graph "as of" a date (doc 02 §6).
- Path mode: pick two nodes → shortest typed path.
- Performance guard: cap rendered nodes; "expand" is explicit, never auto-exploding supernodes.

### 3.7 Collectors `/collectors`
**Purpose:** fleet health & control (FR-UI-5, FR-OPS-1). **Data:** `/v1/admin/collectors`.
- Table: collector, source, enabled toggle, cadence, last run, throughput (docs/min), error rate, source-health status light.
- Row actions: enable/disable, edit cadence, "Run now" (→ job), view recent runs.
- Detail drawer: recent job history, error samples, checkpoint/cursor state.

### 3.8 Jobs `/jobs` (+ DLQ)
**Data:** `/v1/admin/jobs`, `/v1/admin/dlq`, `/v1/admin/pipeline/lag`.
- Jobs table (status/kind/collector/timing/trace_id); filter by status.
- **Pipeline lag panel:** per-topic consumer lag bars (the master health metric, blueprint §22).
- **DLQ inspector:** dead-lettered items with error + payload; "Replay" action.

### 3.9 Review Queue `/review` (Entity Resolution)
**Purpose:** operator adjudication of borderline merges (doc 04 §11). **Data:** `/v1/admin/resolution/review`.
- Card per pair: **side-by-side** entity attributes with differences highlighted, the deciding **features** (match_prob, domain/handle/name similarity), and **evidence** for each side.
- Actions: **Merge** / **Not a match** (→ decision + training label). Keyboard `m`/`n` for speed.
- Also: manual merge search + un-merge from an entity page (doc 06 §4.4).

### 3.10 Keywords `/keywords`
CRUD over tracked terms/pain points (`/v1/admin/keywords`): term, kind, weight, enabled. Shows signal volume per keyword (which keywords are producing opportunities) to guide tuning.

### 3.11 Scoring `/scoring`
**Purpose:** tune ranking without redeploy (FR-SCORE-3, doc 05 §8). **Data:** `/v1/admin/scoring/weights`.
- Sliders/inputs for OS weights (w1..w7), tier multipliers, decay τ per signal type, intent weights, ER thresholds.
- **Live preview:** apply to a sample of opportunities and show re-ranked order before saving (guards against bad weights).
- Save → confirmation ("this will rescore N opportunities in the background") + audit note. History of prior configs.

### 3.12 Settings `/settings`
Sources config, digest schedule/recipient, freshness targets per source, feature flags, cost/budget caps display.

---

## 4. Core Component Library

| Component | Purpose |
|---|---|
| `TierBadge` | Gold/Silver/Bronze pill with consistent color semantics |
| `TierFilter` | segmented control (Gold/Silver/Bronze/All), URL-synced |
| `ScoreBar` + `ScoreBreakdownPopover` | composite score + expandable 8-sub-score explanation (U5) |
| `EvidenceChip` | source icon · snippet · confidence · date · external link (U1) |
| `EvidenceList` | grouped, filterable by claim_type |
| `LineageDrawer` | raw→parsed→evidence→canonical chain for an attribute |
| `FreshnessBadge` | relative age + decay indicator (U7) |
| `TimelineView` | vertical chronological events with signal icons (U3) |
| `TransitionLedger` | promotion/demotion arc with reasons + deltas |
| `FacetBar` | multi-select facets bound to search aggregations |
| `EntityCard` / `EntityAvatar` | company/person compact rep |
| `GraphCanvas` | interactive graph with typed nodes/edges + evidence popovers |
| `ProvenanceHover` | shows survivorship `alternatives` on any canonical field |
| `DataTable` | dense, keyboard-navigable, cursor-paginated table |

---

## 5. Interaction & State Patterns

- **Data fetching:** server components for initial load; TanStack Query for client-side pagination/refetch; optimistic UI on admin toggles.
- **URL as state:** all filters/sorts/tabs live in the URL (shareable, restorable, back-button correct).
- **Loading:** skeletons, never spinners-on-blank for lists; suspense boundaries per region.
- **Empty:** actionable copy ("widen filters", "no signals yet — collectors run hourly").
- **Error:** inline, retryable; `trace_id` shown in a copyable detail for debugging.
- **Live-ish:** ops pages (Jobs/Collectors) poll or subscribe (SSE) for status; the board shows a "new opportunities available — refresh" toast rather than auto-reflowing under the operator.
- **Keyboard-first:** j/k navigation, ⌘K palette, single-key actions in review queue.

---

## 6. Design System

- **Layout:** left nav rail + dense content area; max information density without clutter.
- **Color semantics:** Gold `#C9A227`, Silver `#8A94A6`, Bronze `#B87333`; signal-strength heat (green→amber→red for pain intensity); confidence as opacity/fill. Follow the `dataviz` skill's palette guidance for any charts (promotion funnel, freshness distribution, evidence density trends on a small analytics strip).
- **Theme:** light + dark, respecting `prefers-color-scheme`.
- **Accessibility:** WCAG AA contrast, keyboard operability, ARIA on interactive graph/tables, never color-only encoding (pair color with icon/label).
- **Typography:** system UI stack; tabular numerals for scores; monospace for IDs/hashes/URLs.
- **Charts:** thin analytics strip on Dashboard (Gold/Silver/Bronze counts + daily delta, promotion rate, freshness histogram) — built per the `dataviz` skill.

---

## 7. Performance

- List/search render from API in < 400 ms P95 (NFR-6); virtualize long tables/graph.
- Entity pages: single GraphQL round-trip (doc 06 §5.2) to avoid waterfalls.
- Cache-aware: respect `ETag`/version; show freshness of cached data.
- Graph canvas: cap nodes, lazy-expand, web-worker layout for large neighborhoods.

---

## 8. Daily Digest (surface)
A digest view/email (`digest` worker, blueprint §18) summarizing **new** and **upgraded** opportunities since yesterday, linking into the board pre-filtered. Rendered from `opportunity_transition` (upgrades) + new Gold/Silver. The in-app bell opens the same content.

---

## 9. SaaS Readiness (additive)
Nav, filters, and pages are workspace-agnostic; adding tenancy later = a workspace switcher + scoping saved views/keywords/scoring per tenant (the graph pages stay global). Auth screens are a thin addition ahead of the router (blueprint §27).

---

## 10. Open Questions / ADRs
- **ADR-UI-1:** graph rendering lib (Cytoscape vs. react-force-graph vs. sigma.js) — evaluate at ~1k visible nodes.
- **ADR-UI-2:** SSE vs. polling for live ops status.
- **ADR-UI-3:** in-app digest only vs. email delivery in v1.
- **ADR-UI-4:** inline editing of survivorship (operator overrides a canonical value) — powerful but must stay evidence-backed/audited.
