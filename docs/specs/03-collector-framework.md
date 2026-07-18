# 03 — Collector Framework Specification

> **Master spec:** [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §13 · Pipeline: §14 · Scheduler: §19
> **Status:** Implementation-ready
> **Prime directive:** *Adding a new source must never require changing the core.* Collectors are plugins; the runtime injects every cross-cutting concern.

---

## 1. Design Goals & Principles

| Goal | Consequence |
|---|---|
| **Unlimited, pluggable sources** | Collectors discovered via a registry; one package per source under `packages/collectors/sources/`. |
| **Author writes only source-specific logic** | Runtime owns retry, rate-limit, robots, dedupe, raw persistence, event emission, metrics, tracing, checkpointing, recovery. |
| **Raw is sacred** | Raw bytes persisted to S3 *before* any parsing (blueprint I: never delete raw). |
| **Idempotent & replayable** | Emission keyed on `content_hash`; re-running a collector converges, never double-counts. |
| **Polite by construction** | Per-host rate limits and robots enforced by the runtime, not left to authors. |
| **Deterministic-first extraction** | Structured parsers before LLM; LLM gated by budget + prefilter. |

**Inversion of control is the core idea:** the collector is a set of pure-ish functions; the runtime is the engine that calls them with all concerns handled. This is what keeps a fleet of dozens–hundreds of sources maintainable.

---

## 2. The Collector Contract

```python
# packages/collectors/base/collector.py
from typing import Protocol, Iterable

class Capabilities(TypedDict, total=False):
    supports_incremental: bool     # honors ETag/Last-Modified/cursor
    needs_browser: bool            # requires Playwright (JS render)
    auth_kind: str | None          # 'none' | 'api_key' | 'oauth'
    politeness_class: str          # 'gentle' | 'standard' | 'aggressive-with-api'
    max_concurrency: int           # per-source cap hint

class BaseCollector(Protocol):
    source_slug: str               # stable identity, FK to `source`
    collector_slug: str            # FK to `collector`
    version: str                   # semver; part of extraction idempotency key
    capabilities: Capabilities

    def plan(self, ctx: "CollectorContext") -> Iterable["FetchTask"]:
        """Discovery & seed expansion. Yields the URLs/API calls to fetch.
           May read crawl_state cursor for incremental planning."""

    def fetch(self, task: "FetchTask", ctx) -> "RawResponse":
        """Network I/O only. Returns raw bytes + headers + status.
           Uses ctx.http / ctx.browser (runtime-provided, rate-limited)."""

    def parse(self, raw: "RawResponse", ctx) -> "ParsedDocument":
        """Bytes -> structured document (clean text, links, structured fields)."""

    def normalize(self, doc: "ParsedDocument", ctx) -> list["CandidateRecord"]:
        """ParsedDocument -> candidate entities/signals, each carrying Evidence."""

    def checkpoint(self, ctx) -> "Cursor":
        """Return the resumable cursor to persist after a batch."""
```

**What the author does NOT implement** (runtime-owned): HTTP client construction, retry/backoff, rate-limit gating, robots checks, raw persistence, event emission, dedupe, metrics, tracing, logging, DLQ, recovery/resume. The author *uses* `ctx` handles and returns data.

### 2.1 Supporting types
```python
@dataclass
class FetchTask:
    url: str
    method: str = "GET"
    headers: dict | None = None
    seed_key: str | None = None          # groups checkpoints in crawl_state
    priority: int = 0                    # scheduler hint (value*staleness)
    render: bool = False                 # force browser

@dataclass
class RawResponse:
    url: str; status: int; headers: dict
    body: bytes; content_type: str; fetched_at: datetime
    content_hash: bytes                  # sha256(body), set by runtime

@dataclass
class CandidateRecord:
    kind: str                            # 'entity' | 'signal'
    entity_type: str | None              # for entity kind
    signal_type: str | None              # for signal kind
    attributes: dict
    evidence: EvidenceDraft              # url, snippet, claim_type, confidence  (MANDATORY)
    blocking_hints: dict | None          # apex_domain, handle... to seed ER
```

`CandidateRecord.evidence` is **non-optional** — the type system encodes invariant I2 ("no claim without evidence"). A collector cannot emit a claim without proof.

---

## 3. Lifecycle (runtime-driven)

```
                 ┌──────────────────────────── Temporal Workflow: collect(collector, seeds) ───────────────────────────┐
plan(ctx) ──► [for each FetchTask, priority-ordered] :
                 │
                 ├─ rate-limit gate (per-host token bucket, Redis)            ── ctx.rate_limiter
                 ├─ robots check (cached, honor crawl-delay / Retry-After)     ── ctx.robots
                 ├─ conditional GET (ETag/Last-Modified from crawl_state)      ── ctx.crawl_state
                 ├─ dedupe (content_hash seen? skip)                           ── ctx.dedupe
                 │
                 ├─ fetch(task) with retry+backoff+timeout+heartbeat          ── ctx.http / ctx.browser
                 │       └─ on RawResponse: persist RAW → S3 + raw_document    ── ctx.raw_store   (BEFORE parsing)
                 │       └─ emit  raw.fetched{raw_ref, content_hash, ...}       ── ctx.bus
                 │
                 ├─ checkpoint(ctx) → persist cursor/etag to crawl_state       ── every N tasks
                 └─ metrics + structured log per task (trace_id propagated)
                 ▼
 (async, downstream workers — not the collector):
   raw.fetched ─► parse() ─► normalize() ─► emit entities.candidate / signals.candidate
```

Parsing/normalization run in the **parser/extractor** workers consuming `raw.fetched` (decoupled from fetch), so a slow parser never blocks polite fetching and reprocessing never re-crawls. A collector's `parse`/`normalize` are invoked by those workers via the same plugin instance.

---

## 4. Cross-Cutting Concerns (runtime specification)

### 4.1 Retry & backoff
- Error taxonomy: **retryable** (network, timeout, 5xx, 429) vs **permanent** (4xx≠429, parse error, robots-denied).
- Exponential backoff with full jitter: `delay = min(cap, base·2^attempt) · U(0,1)`; `base=1s, cap=60s`, max attempts per policy (default 5).
- `429`/`Retry-After` honored exactly (overrides backoff).
- After max attempts → **dead-letter** (`job.status='dead'` + DLQ topic) with full context; never blocks the workflow.

### 4.2 Checkpointing & recovery
- Cursor persisted per `(collector_id, seed_key)` in `crawl_state` after each batch.
- Temporal workflow durability + heartbeats: a crashed worker's workflow resumes from the last checkpoint; in-flight fetches reclaimed by visibility timeout.
- Idempotent emission on `content_hash` guarantees resume never double-emits.

### 4.3 Rate limiting & politeness
- **Per-host token bucket** in Redis (`ratelimit:{host}` → refill rate from source politeness class).
- **Global per-source concurrency cap** (`capabilities.max_concurrency`).
- **Robots**: `robots.txt` fetched, cached (TTL), crawl-delay respected; disallowed paths skipped and logged.
- **Identifying User-Agent** with contact URL; honest crawler identity (blueprint §25).

### 4.4 Deduplication
- **Content-level:** `content_hash` seen-set (Redis bloom + `raw_document(content_hash)` index) → unchanged pages skip parsing.
- **Conditional fetch:** send `If-None-Match`/`If-Modified-Since` from `crawl_state`; `304` → skip.
- **URL-level:** normalized-URL seen-set to avoid re-planning within a run.

### 4.5 Raw persistence (before parse)
- Every `RawResponse` written to S3 at `raw/{source}/{yyyy}/{mm}/{content_hash}` and indexed in `raw_document`, **before** `parse` runs. This is non-negotiable: raw is the replay substrate and the irreplaceable asset.

### 4.6 Observability
- Metrics per collector: `fetched`, `skipped_dedupe`, `robots_blocked`, `retries`, `errors`, `bytes`, `fetch_latency_p50/p95`, `candidates_emitted`.
- Structured logs with `trace_id, source_id, collector_id, url`.
- OpenTelemetry span from `plan`→`fetch`→`emit`, context propagated into the event envelope so downstream stages join the trace (blueprint §23).

### 4.7 Budget & cost guards
- LLM extraction (downstream) honors a **daily token budget**; over-budget → deterministic-only fallback.
- Browser-render tasks isolated to a bounded pool with per-task CPU/memory/time limits.

---

## 5. Fetch Strategies

| Strategy | When | Runtime handle |
|---|---|---|
| **API-first** | source has a public API (GitHub, Reddit, HN Firebase, Product Hunt) | `ctx.http` + typed client; always preferred over HTML |
| **HTTP static** | server-rendered HTML/JSON/RSS | `ctx.http` (httpx, HTTP/2, connection pool) |
| **Headless browser** | `needs_browser` (JS-rendered) | `ctx.browser` (Playwright pool, isolated workers) |
| **Sitemap/feed** | discovery via sitemap.xml / RSS | planner expands feeds into FetchTasks |

Playwright is pre-provisioned in the environment (`PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); the browser pool uses the installed Chromium — never re-downloads.

---

## 6. Collector Registry & Configuration

### 6.1 Registry
```python
# packages/collectors/registry.py
COLLECTORS: dict[str, type[BaseCollector]] = {}

def register(cls):                      # decorator
    COLLECTORS[cls.collector_slug] = cls
    return cls

def load_enabled() -> list[BaseCollector]:
    # instantiate collectors whose `collector` row is enabled
    ...
```
Discovery is by decorator + package scan. Enabling/disabling and cadence come from the `collector` DB row (operator-editable, doc 07 Collectors page). **Adding a source = new package + `@register` + a `collector` row. Zero core edits.** (NFR-8: new collector in < 1 day.)

### 6.2 Per-collector config (declarative)
```yaml
# packages/collectors/sources/github/collector.yaml
source_slug: github
collector_slug: github_issues
version: "1.0.0"
capabilities: { supports_incremental: true, needs_browser: false, auth_kind: api_key, politeness_class: aggressive-with-api, max_concurrency: 8 }
cadence_hint: "PT1H"
seeds:
  strategy: "tracked_companies_with_github_org"
```

---

## 7. Initial Collector Fleet (per blueprint §13.3)

Each is a package implementing the contract. Emitted candidates listed.

| Collector | Source class | Fetch | Emits |
|---|---|---|---|
| `company_web` | homepage/about/team/leadership/careers/pricing/changelog | HTTP (+browser if needed) | company, person, job, technology, product, `works_at`, `owns_domain` |
| `rss_blog` | company blogs, RSS/Atom | HTTP feed | post, person(author), `authored`, `mentions`, launch/funding signals |
| `news` | news/press aggregators | API/HTTP | company, `raised`, `launched`, leadership-change signals |
| `github` | repos/issues/discussions | API-first | company, person, technology, hiring intent, `uses_tech` |
| `hackernews` | HN (Firebase API) | API | `mentions`(pain/interest), person, company mention |
| `reddit` | subreddits | API | pain/interest signals, mentions |
| `producthunt` | launches | API | product, `launched`, company |
| `podcasts` | show/episode pages | HTTP | person, event, `spoke_at` |
| `conferences` | speaker/agenda pages | HTTP (+browser) | person, event, `spoke_at` |
| `funding` | funding feeds/registries | API/HTTP | company, `raised` signal |

### 7.1 Reference implementation sketch (RSS blog)
```python
@register
class RssBlogCollector(BaseCollector):
    source_slug = "company_web"; collector_slug = "rss_blog"; version = "1.0.0"
    capabilities = {"supports_incremental": True, "needs_browser": False,
                    "politeness_class": "standard", "max_concurrency": 4}

    def plan(self, ctx):
        for feed in ctx.seeds.feeds():                      # from crawl_state / tracked companies
            yield FetchTask(url=feed.url, seed_key=feed.host)

    def fetch(self, task, ctx):
        return ctx.http.get(task.url, conditional=True)     # runtime adds ETag/robots/rate-limit

    def parse(self, raw, ctx):
        return ctx.parsers.rss(raw.body)                    # -> ParsedDocument(items=[...])

    def normalize(self, doc, ctx):
        out = []
        for item in doc.items:
            company = ctx.resolver_hint.company_from_host(item.source_host)
            out.append(CandidateRecord(
                kind="entity", entity_type="post",
                attributes={"title": item.title, "url": item.url, "published_at": item.date},
                evidence=EvidenceDraft(url=item.url, snippet=item.title,
                                       claim_type="post.published", confidence=0.9),
                blocking_hints={"apex_domain": item.source_apex}))
            if item.author:
                out.append(CandidateRecord(
                    kind="entity", entity_type="person",
                    attributes={"full_name": item.author},
                    evidence=EvidenceDraft(url=item.url, snippet=f"By {item.author}",
                                           claim_type="person.authored", confidence=0.6),
                    blocking_hints={"name": item.author, "apex_domain": item.source_apex}))
        return out

    def checkpoint(self, ctx):
        return ctx.cursor(last_seen=ctx.max_item_date)
```

---

## 8. Testing a Collector (hooks into doc 09)

| Test | What |
|---|---|
| **Golden fixture** | frozen raw doc → asserted `ParsedDocument` + `CandidateRecord[]` (snapshot) — regression-locks the parser. |
| **Contract test** | collector conforms to `BaseCollector`; emits well-formed candidates; every candidate has evidence. |
| **Politeness test** | runtime honors robots/rate-limit for the collector's politeness class. |
| **Incremental test** | second run with unchanged content → all skipped (dedupe/304). |
| **Recovery test** | kill mid-run → resume from checkpoint with no dup emission. |

Fixtures live in `tests/fixtures/collectors/<slug>/`. CI fails on golden-snapshot drift.

---

## 9. Failure Modes & Handling

| Failure | Runtime response |
|---|---|
| Transient network/5xx/429 | retry+backoff; honor Retry-After |
| Permanent 4xx / robots-denied | skip, log, mark source-health metric |
| Parse error on a doc | DLQ that doc, continue; raw already stored → replayable after parser fix |
| Anti-bot / IP block | back off host, alert source-health; consider API path |
| Source schema change | golden test fails in CI before deploy; raw retained → reprocess after fix |
| Worker crash | Temporal resume from checkpoint |
| Poison message | N failures → DLQ, never blocks partition |

**Key resilience property:** because raw is stored before parsing and parsing is decoupled, *almost every failure is recoverable by reprocessing without re-crawling* — the collector's job (polite fetch) and the parser's job (extraction) fail independently.

---

## 10. Open Questions / ADRs
- **ADR-COL-1:** proxy/rotation policy for anti-bot sources (ethics + politeness constraints).
- **ADR-COL-2:** shared browser pool sizing & isolation (cost vs. throughput).
- **ADR-COL-3:** seed-expansion depth/host caps to prevent crawl explosions.
- **ADR-COL-4:** per-source LLM budget allocation strategy.
