"""Crawl execution (spec 03 / blueprint §19).

The scheduler decides *what* to crawl; an executor *runs* the due crawls on each
tick. ``InProcessExecutor`` runs them inline (fully tested, and usable for local /
single-node operation). ``TemporalExecutor`` submits each crawl as a durable
Temporal workflow — resumable, retried, and observable — for production. Both
implement the same ``Executor`` contract, so the driving loop is identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from core.logging import get_logger

from .planner import CrawlTarget, Scheduler

log = get_logger("scheduler.executor")

# A crawl runner takes a target and returns how many candidates it produced.
CrawlRunner = Callable[[CrawlTarget], int]


@dataclass
class TickResult:
    ran: int = 0
    candidates: int = 0
    errors: int = 0
    seeds: list[str] = field(default_factory=list)


class Executor(Protocol):
    def run_due(self, targets: list[CrawlTarget], runner: CrawlRunner,
                now: datetime | None = None, limit: int | None = None) -> TickResult: ...


class InProcessExecutor:
    """Runs due crawls inline. The Scheduler picks the due set (value×staleness);
    the executor runs each and marks it crawled with a fresh value score."""

    def __init__(self, scheduler: Scheduler | None = None):
        self._scheduler = scheduler or Scheduler()

    def run_due(self, targets, runner, now=None, limit=None) -> TickResult:
        now = now or datetime.now(UTC)
        result = TickResult()
        for target in self._scheduler.plan(targets, now=now, limit=limit):
            try:
                produced = runner(target)
                result.ran += 1
                result.candidates += produced
                result.seeds.append(target.seed_key)
                # Hotter if it produced signal-rich output (cheap proxy: candidates).
                value = min(1.0, produced / 10.0)
                self._scheduler.mark_crawled(target, now=now, value_score=value)
            except Exception as exc:  # noqa: BLE001 - isolate a bad target
                result.errors += 1
                log.warning("crawl failed", extra={"context": {"seed": target.seed_key,
                                                               "err": str(exc)}})
        return result


class TemporalExecutor:
    """Submits each due crawl as a durable Temporal workflow (production).

    Requires a running Temporal server + worker hosting ``CrawlWorkflow`` (see
    workflows.py). Lazily imports the SDK so the domain layer stays dependency-free.
    Not exercised in unit tests (needs the server); the InProcessExecutor covers
    the scheduling/runner contract.
    """

    def __init__(self, client, task_queue: str = "navic-crawls",
                 scheduler: Scheduler | None = None):
        self._client = client
        self._task_queue = task_queue
        self._scheduler = scheduler or Scheduler()

    def run_due(self, targets, runner, now=None, limit=None) -> TickResult:
        import asyncio

        from .workflows import CrawlWorkflow

        now = now or datetime.now(UTC)
        due = self._scheduler.plan(targets, now=now, limit=limit)
        result = TickResult(ran=len(due), seeds=[t.seed_key for t in due])

        async def _submit():
            for t in due:
                await self._client.start_workflow(
                    CrawlWorkflow.run, args=[t.collector_slug, t.seed_key],
                    id=f"crawl-{t.collector_slug}-{t.seed_key}", task_queue=self._task_queue,
                )

        asyncio.get_event_loop().run_until_complete(_submit())
        return result
