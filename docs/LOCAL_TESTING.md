# Testing NavIC locally with Docker

This guide gets NavIC running on your own computer so you can click through the
product yourself. You do **not** need to be technical, and you do **not** need to
install Python, Node, or a database — Docker does all of it.

There are three paths:

1. **[Quick demo](#1-quick-demo-one-command)** — one command, no database. Best for
   "show me it works." *(This is the one to start with.)*
2. **[Run the automated tests](#2-run-the-automated-test-suite)** — proves the code
   is healthy (the 155 tests).
3. **[Full stack](#3-full-stack-with-a-real-database-advanced)** — the real Postgres +
   graph + search services. For later, when you want the production-shaped setup.

---

## Prerequisites (one-time, 5 minutes)

Install **Docker Desktop** — it bundles everything (`docker` + `docker compose`):

- **Mac / Windows:** download from <https://www.docker.com/products/docker-desktop/>,
  run the installer, then launch Docker Desktop and wait until the whale icon in the
  menu bar / system tray stops animating (that means the engine is running).
- **Linux:** install Docker Engine + the Compose plugin per
  <https://docs.docker.com/engine/install/>.

Verify it's ready — open a terminal and run:

```bash
docker --version
docker compose version
```

Both should print a version number. If `docker` says it can't connect to the daemon,
Docker Desktop isn't running yet — start it and wait.

Then get the code (if you don't already have it):

```bash
git clone <your-repo-url> navic
cd navic
git checkout claude/opportunity-intelligence-platform-mh9jb3
```

---

## 1. Quick demo (one command)

From the project folder (`navic`), run:

```bash
docker compose -f docker-compose.demo.yml up --build
```

The first run takes a few minutes (it downloads and builds the two images). You'll see
lots of log lines scroll by — that's normal. Wait until you see something like:

```
navic-api-1        | [demo] seeded {'companies': 14, 'signals': 29, 'opportunities': 15} | tiers={'gold': 1, 'silver': 4, 'bronze': 9}
navic-api-1        | INFO:     Uvicorn running on http://0.0.0.0:8000
navic-dashboard-1  |   ▲ Next.js 14.2.5
navic-dashboard-1  |   - Local:        http://localhost:8480
```

> The `8000` / `3000` in those log lines are the ports **inside** the containers.
> From your browser you use the demo's own ports below (`8480` / `8481`), chosen to
> avoid clashing with other projects you may run on `3000`, `5173`, or `8000`.

Now open **<http://localhost:8480>** in your browser.

### What you should see

| Page | URL | What it shows |
|------|-----|---------------|
| **Opportunities** | <http://localhost:8480> | The ranked board — a **Gold** opportunity (Wayne Analytics, with the decision-maker Lucius Fox), several **Silver**, and **Bronze** early signals. Every card lists the evidence behind it. Use the Gold/Silver/Bronze filter buttons. |
| **Search** | <http://localhost:8480/search> | Click *"companies hiring SDR"*. Notice it prints **`Interpreted as: hiring:Sales`** — it turned plain English into a structured filter — then lists matching companies with evidence. |
| **Graph** | <http://localhost:8480/graph> | Type `13` and click **Load** to see Wayne Analytics connected to its people by `works_at` relationships — the knowledge graph. |
| **Collectors** | <http://localhost:8480/collectors> | All **10 data sources** the platform can pull from (company sites, GitHub, Hacker News, Reddit, Product Hunt, LinkedIn, Greenhouse job boards, news, funding databases, RSS blogs). |
| **Review** | <http://localhost:8480/review> | The human-in-the-loop queue for borderline "are these the same company/person?" decisions. Empty in the demo (nothing ambiguous). |

You can also hit the API directly:

- Health check: <http://localhost:8481/health>
- Raw opportunities data: <http://localhost:8481/v1/opportunities>
- Gold only: <http://localhost:8481/v1/opportunities?tier=gold>

### Stopping it

Press **Ctrl+C** in the terminal, then (to remove the containers):

```bash
docker compose -f docker-compose.demo.yml down
```

> **About the demo data:** the quick demo is seeded with a fixed set of realistic
> **sample** signals so the board looks the same every time — it is not pulling from
> the live internet. That is deliberate: it isolates the product from network flakiness
> so you're testing NavIC, not your Wi-Fi. The live collectors (which do fetch real
> public data on a schedule) are exercised by the automated test suite below and run in
> the full-stack setup.

---

## 2. Run the automated test suite

This proves the engine itself is correct — entity resolution, scoring, tiering, all 10
collectors, the API. It runs the same 155 tests I run during development, inside Docker,
so you don't need Python installed:

```bash
docker run --rm -v "$PWD":/app -w /app python:3.11-slim bash -c \
  "pip install -q -e '.[dev]' && python -m pytest -q"
```

You should see a line like `155 passed` at the end. (The first run installs
dependencies, so give it a couple of minutes.)

---

## 3. Full stack with a real database (advanced)

The quick demo skips the database on purpose. When you want the production-shaped setup
— PostgreSQL with the Apache AGE graph extension, plus Redis, MinIO, and OpenSearch —
use the main compose file, which starts those services:

```bash
# 1. Start the data services (Postgres+AGE, Redis, MinIO, OpenSearch)
docker compose up -d

# 2. Create the database schema (run once)
docker run --rm --network host -v "$PWD":/app -w /app python:3.11-slim bash -c \
  "pip install -q -e . && NAVIC_DATABASE_URL=postgresql+psycopg://navic:navic@127.0.0.1:5432/navic \
   alembic -c alembic.ini upgrade head"
```

At that point the database is live and migrated. Wiring the API container to Postgres
(instead of the in-memory store) is done by setting `NAVIC_API_BACKEND=postgres` and
`NAVIC_DATABASE_URL=...` on the API service — that path is for when you move past
local evaluation toward a deployment.

To stop and remove the data services:

```bash
docker compose down          # add -v to also delete the stored data
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker: Cannot connect to the Docker daemon` | Docker Desktop isn't running. Start it and wait for the whale icon to settle. |
| **I open the page and see a *different / older* project** | Another app is already using that port, or your browser cached one. This demo uses **8480 / 8481** specifically to avoid the common ports (3000, 5173, 8000). Make sure you're opening **<http://localhost:8480>** — not 3000. Still stale? Open it in a **private/incognito window** (bypasses cache), or stop the other dev server first. |
| `port is already allocated` (8480 or 8481) | Even these ports are taken. Pick your own and rebuild: `NAVIC_DASHBOARD_PORT=9480 NAVIC_API_PORT=9481 docker compose -f docker-compose.demo.yml up --build`, then open <http://localhost:9480>. |
| Dashboard loads but shows *"Failed to load"* | The API container may still be starting. Refresh after a few seconds. Confirm <http://localhost:8481/health> returns `{"status":"ok"}`. |
| First build is slow | Expected — it downloads base images and installs dependencies once. Subsequent runs are fast. |
| Want a clean rebuild | `docker compose -f docker-compose.demo.yml build --no-cache` |
