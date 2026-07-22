# Going live: what each source needs

The engine is source-agnostic. Each collector already declares how it authenticates
(`capabilities.auth_kind` — none / `api_key` / `oauth`), and the fetch client accepts
per-request headers, so "going live" on a source is: **get the credential → put it in
config → point the scheduler at a seed list.** Credentials live as `NAVIC_*` environment
variables (see `packages/core/config.py`); nothing is hard-coded.

This document is the honest, source-by-source map: what account you need, what it costs,
the rate limits, the legal footing, and how much work each one is. Sources are grouped
by how hard they are to turn on.

> **The one rule that governs all of this:** public data only, and every source's Terms
> of Service and `robots.txt` honored. That rule is what keeps this a legitimate
> intelligence platform rather than a scraper — and it's the reason LinkedIn (below) is
> the hard case, not a quick win.

---

## Readiness at a glance

| Source | Auth | Cost to start | Effort | Notes |
|---|---|---|---|---|
| **company_web** | none | free | 🟢 ready | Public pages; honor robots.txt + crawl-delay |
| **rss_blog** | none | free | 🟢 ready | Public RSS/Atom feeds |
| **hackernews** | none | free | 🟢 ready | Official Firebase/Algolia API, no key |
| **hn_freelance** | none | free | 🟢 ready | Auto-monitors HN "Seeking Freelancer" buyer posts via the free Algolia API |
| **greenhouse** | none | free | 🟢 ready | Public job-board API |
| **lever / ashby / workable** | none | free | 🟢 ready | Public job-board APIs (same pattern as Greenhouse) |
| **remoteok / weworkremotely / remotive** | none | free | 🟢 ready | Broad remote-hiring feeds (public APIs / RSS); anchor on the company domain from the apply link, else on the company name |
| **hn_search** | none | free | 🟢 ready | Key-less requirement firehose — searches all of Hacker News for "looking for a…" posts via the free Algolia API |
| **reddit_search / reddit_forhire** | none (dev) | free | 🟢 ready | Public Reddit search + hiring subreddits for buyers posting requirements (production wants a free Reddit app) |
| **bluesky** | none | free | 🟢 ready | Key-less public search (public.api.bsky.app) for "looking for a…" posts across Bluesky |
| **github** | API key (PAT) | free | 🟢 easy | 5,000 req/hr authenticated |
| **producthunt** | OAuth token | free | 🟢 easy | Official API v2 (GraphQL) |
| **reddit** | OAuth app | free tier | 🟡 medium | API terms tightened; commercial use may need an agreement |
| **news** | API key | free–paid | 🟡 medium | GDELT free to start; NewsAPI/Bing paid for commercial |
| **funding** | API key | free–$$$ | 🟡 medium | SEC EDGAR free; Crunchbase paid |
| **linkedin** | partner/OAuth | — | 🔴 constrained | **No official API for public member posts** — see below |

🟢 = works with little/no setup · 🟡 = needs an account + light integration · 🔴 = legally constrained, needs a different approach

---

## Tier A — turn on today (no credentials)

These need nothing but a seed list and the scheduler running.

### company_web
- **Auth:** none. **Cost:** free (bandwidth only).
- **What to provide:** a list of company domains to crawl (your ICP list, or discovered
  from the other sources).
- **Compliance:** fetch `robots.txt` first and honor `Disallow` + `Crawl-delay`; identify
  with a real User-Agent (the fetch client already sends `NavicBot/...`). Only public
  pages — never anything behind a login.
- **Effort:** the collector and polite HTTP client already exist; you add a robots.txt
  gate and a domain seed list.

### rss_blog
- **Auth:** none. **Cost:** free.
- **What to provide:** feed URLs (company blogs, industry news feeds).
- **Compliance:** feeds are published for consumption; still cache with `ETag`/`If-Modified-Since`.

### hackernews
- **Auth:** none. **Cost:** free.
- **API:** the official [HN Firebase API](https://github.com/HackerNews/API) (`hacker-news.firebaseio.com`)
  or the Algolia HN Search API for querying. No key, generous limits.

### greenhouse (and other job boards)
- **Auth:** none for the **public** board API: `https://boards-api.greenhouse.io/v1/boards/<token>/jobs`.
- **What to provide:** the list of company board tokens to watch. The same pattern works
  for **Lever**, **Ashby**, and **Workable**, which also expose public board JSON — each
  is a ~30-line collector added the same way.
- **Compliance:** these endpoints are published for exactly this use; stay within polite
  request rates.

---

## Tier B — a free account + a key

### github
- **Auth:** a Personal Access Token (create at *GitHub → Settings → Developer settings →
  Personal access tokens*), or a GitHub App for higher limits.
- **Rate limit:** 5,000 requests/hour authenticated (60/hr unauthenticated).
- **Cost:** free. **Legal:** a first-party, sanctioned API.
- **Wire-up:** add `NAVIC_GITHUB_TOKEN` to config; the fetch client sends
  `Authorization: Bearer <token>`.

### producthunt
- **Auth:** OAuth2 developer token (register an app in the Product Hunt API dashboard).
- **Cost:** free for reasonable use. **API:** v2 GraphQL.
- **Wire-up:** `NAVIC_PRODUCTHUNT_TOKEN`.

### reddit
- **Auth:** OAuth2 — register a "script" app at <https://www.reddit.com/prefs/apps> to get
  a `client_id` + `client_secret`; requests use a token + a descriptive User-Agent.
- **Rate limit:** ~100 queries/minute per OAuth client on the free tier.
- **⚠️ Legal:** since 2023 Reddit's Data API terms restrict commercial use and bulk
  access; sustained commercial usage may require a formal agreement with Reddit. Read the
  [Data API Terms](https://redditinc.com/policies/data-api-terms) before production use.
  The best-fit subreddits for buying intent are the service-request ones (e.g. r/forhire,
  r/DesignJobs, industry subs).
- **Wire-up:** `NAVIC_REDDIT_CLIENT_ID`, `NAVIC_REDDIT_CLIENT_SECRET`.

### news
- **Free start:** [GDELT](https://www.gdeltproject.org/) — a free, public global news
  index with an API; good for coverage without a bill.
- **Paid options:** NewsAPI.org, Bing News Search, or a licensed newswire — needed for
  commercial redistribution and better freshness/entity tagging.
- **Note:** the collector expects each article tagged with its **subject company**. Free
  feeds often aren't tagged, so you add a light entity-resolution step (match the article's
  named company to a domain) — or pay for a feed that tags entities.
- **Wire-up:** `NAVIC_NEWS_API_KEY` (or none for GDELT).

### funding
- **Free sources:** **SEC EDGAR** Form D filings (US private raises, fully public and free)
  and funding detected from the **news** collector (the regex/LLM funding classifier).
- **Paid source:** the **Crunchbase** API is the gold standard but is an enterprise
  contract (expensive). Start free (EDGAR + news), add Crunchbase later if the ROI is there.
- **Wire-up:** `NAVIC_CRUNCHBASE_KEY` (optional).

---

## Tier C — the LinkedIn reality (read this carefully)

**This is the honest part, and it's important because your examples are LinkedIn posts.**

LinkedIn does **not** offer an API that lets you read arbitrary public member posts —
including the "can anyone recommend a web designer?" posts you shared. Their official APIs
(the Marketing Developer Platform, Community Management API, Sign In with LinkedIn) are
partner-gated and only expose:

- **your own** company page's data,
- an authenticated member's **own** profile/connections (with their explicit consent),
- advertising and page-analytics data.

There is **no sanctioned endpoint** for "search everyone's public posts for buying
intent." And scraping the logged-in LinkedIn site to get it **violates LinkedIn's User
Agreement** — LinkedIn actively pursues this (they win contract claims even where scraping
of *truly public* data survives, per the *hiQ v. LinkedIn* saga). Building that would put
the company at legal risk and betrays the platform's public-data-only principle. **I won't
build it, and you shouldn't operate it.**

So for the LinkedIn *use case* (public service-request posts), the compliant paths are:

1. **Licensed data providers.** Vendors that resell LinkedIn-derived or social data under
   their own agreements (e.g. firmographic/intent-data providers). You buy access; they
   carry the compliance. This is the realistic way to get LinkedIn-shaped signal legally.
2. **The same intent from open sources.** The *behavior* you want — people publicly asking
   to hire a service — happens on channels with real APIs:
   - **Reddit** service-request subreddits (r/forhire, r/DesignJobs, niche subs),
   - **X/Twitter** API (posts asking for recommendations) — the X API is paid,
   - **Indie Hackers, Discourse forums, Facebook Groups** (some with APIs / ToS limits),
   - **freelance marketplaces** (Upwork RSS/exports, Contra) where the request *is* the post,
   - **Programmable web search** (Google/Bing Custom Search) over public post pages.
3. **Consent-based / first-party.** If a user connects *their own* LinkedIn account
   (official OAuth), you can process what they're authorized to see — useful for a
   "monitor my own network" feature, not for whole-platform discovery.
4. **Your own company page** via the Community Management API — legitimate, but narrow.

**Bottom line:** the engine already turns a LinkedIn-style post into a Gold opportunity
(you saw it). The gap is purely *lawful acquisition at scale* — and the answer is a
licensed provider or the open-source equivalents above, not scraping LinkedIn.

---

## The always-on deployment

Turning "runs on my laptop" into "runs 24/7" is four pieces — three already exist in this
repo:

1. **Data services** (`docker-compose.yml`, already here): PostgreSQL + Apache AGE (system
   of record + graph), OpenSearch (search), Redis, MinIO (raw-document object store).
2. **The scheduler + worker** (`packages/scheduler`, already here): the adaptive scheduler
   plans crawls by value×staleness; the **Temporal** executor runs them durably (retries,
   isolation). Going live = running a long-lived worker process pointed at Temporal.
3. **Credentials/secrets** (the new part): the `NAVIC_*` variables above, held in a secret
   store (cloud secrets manager, or a `.env` that never enters git). No code changes —
   they're read by `core.config`.
4. **A host**: a small always-on VM or container platform (a single modest box runs all of
   the above to start; scale out per `docs/ARCHITECTURE.md §21`).

Per-source cadence is config, not code: high-value/fast-moving sources (funding, job
boards, solicitation feeds) poll often; slow ones (company homepages) poll rarely. The
scheduler already expresses this.

---

## Legal & privacy layer (do this before scaling)

Because the platform stores information about **people**, going live means standing up a
compliance posture — this is a business/legal task, not just code:

- **Public-data-only + ToS/robots** enforcement on every collector (the core rule above).
- **GDPR / CCPA:** a lawful basis for processing personal data, a way to honor
  access/deletion requests (the entity model supports un-merge and delete), data-retention
  limits, and a public privacy policy. Get counsel before onboarding EU/California data.
- **Per-source Terms** review: each provider's terms bound what you may store and
  redistribute (Reddit, Crunchbase, and news feeds each differ). Keep evidence provenance
  (the platform already stores source URL + timestamp per claim) so any datum is traceable.

---

## Recommended rollout

1. **Week 1 — free sources, no keys:** company_web, rss_blog, hackernews, greenhouse
   (+ Lever/Ashby). Immediate live signal, zero cost, zero legal ambiguity.
2. **Week 2 — free accounts:** add github + producthunt tokens; add news via GDELT and
   funding via SEC EDGAR.
3. **Week 3 — evaluate paid/constrained:** decide on reddit (terms), a paid news feed, and
   Crunchbase based on early ROI.
4. **For the LinkedIn use case:** pilot a licensed intent-data provider and/or the Reddit +
   X + freelance-marketplace collectors, which capture the same "asking to buy" behavior
   lawfully.
5. **Before onboarding real personal data at scale:** the privacy/legal layer above.

The engineering to *consume* every one of these is the same small collector pattern you've
already seen five times. The gating factors are **credentials, cost, and terms** — which is
exactly what this document lays out so you can decide source by source.
