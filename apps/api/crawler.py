"""On-demand crawl runner (operator-controlled Start/Stop).

Not a 24/7 daemon: the operator presses Start and a background thread runs one crawl
cycle immediately, then repeats every `interval` seconds until Stop. Each cycle runs
the configured collectors with a real HTTP fetch client and drives the results through
the same pipeline the API serves, so new leads appear on the board within seconds.

Designed for local, single-operator use (run it for days on a laptop, stop it when
done). State is in-process; a Stop — or quitting the app — ends it.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from core.logging import get_logger
from ingestion import HttpFetchClient, InMemoryRawStore

log = get_logger("api.crawler")


# A source is (collector slug, seed URLs, {url: company dict}) — the company map is
# populated for job boards, whose live API responses don't carry the company domain.
Source = tuple[str, list[str], dict]


def _default_sources() -> list[Source]:
    """Registered collectors that ship with default seeds (ready to run with no
    per-company config) — today the community monitors (HN freelancer, r/forhire)."""
    import collectors.sources  # noqa: F401
    from collectors import REGISTRY
    from collectors.registry import get_collector

    out: list[Source] = []
    for slug in sorted(REGISTRY):
        seeds = list(getattr(get_collector(slug), "_seeds", []) or [])
        if seeds:
            out.append((slug, seeds, {}))
    return out


def _sources_from_targets(targets) -> list[Source]:
    """Group operator seed targets by collector into runnable sources; attach the
    company each job-board URL should anchor to."""
    by_slug: dict[str, dict] = {}
    for t in targets:
        entry = by_slug.setdefault(t.source, {"seeds": [], "company_for": {}})
        entry["seeds"].append(t.url)
        if t.company_domain:
            entry["company_for"][t.url] = {
                "name": t.company_name or t.company_domain,
                "website": t.company_domain, "careers_url": t.url}
    return [(slug, e["seeds"], e["company_for"]) for slug, e in by_slug.items()]


class CrawlerManager:
    def __init__(self, provider_getter, fetch_factory=HttpFetchClient, seeds_provider=None):
        self._provider_getter = provider_getter
        self._fetch_factory = fetch_factory
        self._seeds_provider = seeds_provider  # () -> list[Target]; falls back to defaults
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._interval = 45
        self._sources: list[Source] = []
        self._state: dict = {
            "running": False, "started_at": None, "cycles": 0, "last_run_at": None,
            "totals": {"companies": 0, "signals": 0, "opportunities": 0},
            "per_source": {}, "last_error": None,
        }

    def _resolve_sources(self) -> list[Source]:
        targets = list(self._seeds_provider()) if self._seeds_provider else []
        return _sources_from_targets(targets) if targets else _default_sources()

    # ---- control ---------------------------------------------------------
    def start(self, interval: int | None = None,
              sources: list[Source] | None = None) -> dict:
        with self._lock:
            if self._state["running"]:
                return self.status()
            self._interval = max(10, int(interval or self._interval))
            self._sources = sources or self._resolve_sources()
            self._stop.clear()
            self._state.update(running=True, started_at=datetime.now(UTC).isoformat(),
                               cycles=0, last_error=None)
        self._thread = threading.Thread(target=self._loop, name="navic-crawler", daemon=True)
        self._thread.start()
        return self.status()

    def stop(self) -> dict:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=10)
        with self._lock:
            self._state["running"] = False
        return self.status()

    def status(self) -> dict:
        with self._lock:
            # The true number of DISTINCT leads currently on the board (matches the
            # export). `totals` below is cumulative crawl activity across cycles and
            # will be larger because idempotent re-scans re-evaluate the same leads.
            board_total = None
            try:
                with self._provider_getter().bundle() as r:
                    board_total = len(r.opportunities.list())
            except Exception:  # noqa: BLE001  (status must never fail)
                board_total = None
            s = dict(self._state)
            s["interval"] = self._interval
            s["sources"] = [slug for slug, _, _ in self._sources]
            s["board_total"] = board_total
            return s

    # ---- run loop --------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            self._run_cycle()
            self._stop.wait(self._interval)

    def _run_cycle(self) -> None:
        import collectors.sources  # noqa: F401  (ensure collectors are registered)
        from collectors import CollectorRuntime
        from collectors.registry import get_collector
        from collectors.runtime import make_context
        from core.eventbus import InMemoryEventBus

        per_source: dict = {}
        cycle_tot = {"companies": 0, "signals": 0, "opportunities": 0}
        for slug, seeds, company_for in self._sources:
            if self._stop.is_set():
                break
            try:
                collector = get_collector(slug)
                collector._seeds = seeds
                if company_for:
                    collector._company_for = company_for
                fetch = self._fetch_factory()
                ctx = make_context(collector.source_slug, fetch, InMemoryRawStore(),
                                   trace_id="crawl")
                collected = CollectorRuntime(collector, ctx, InMemoryEventBus()).run()
                run_hash = collected.raw_refs[0].content_hash if collected.raw_refs else slug
                with self._lock, self._provider_getter().bundle() as r:
                    result = r.pipeline.ingest(collected.candidates, content_hash=run_hash)
                counts = {"companies": result.companies, "signals": result.signals,
                          "opportunities": len(result.opportunities)}
                per_source[slug] = {"ok": True, **counts}
                for k in cycle_tot:
                    cycle_tot[k] += counts[k]
            except Exception as exc:  # noqa: BLE001  (isolate a bad source; keep crawling)
                log.info("crawl source failed",
                         extra={"context": {"source": slug, "err": str(exc)}})
                per_source[slug] = {"ok": False, "error": str(exc)[:200]}
                with self._lock:
                    self._state["last_error"] = f"{slug}: {str(exc)[:160]}"

        with self._lock:
            self._state["cycles"] += 1
            self._state["last_run_at"] = datetime.now(UTC).isoformat()
            self._state["per_source"] = per_source
            for k in cycle_tot:
                self._state["totals"][k] += cycle_tot[k]
