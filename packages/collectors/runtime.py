"""Collector runtime (spec 03 §3).

Drives the lifecycle: plan -> [dedupe -> fetch -> persist RAW (before parse) ->
emit raw.fetched -> parse -> normalize -> emit candidates]. Owns the
cross-cutting concerns so collectors stay source-specific. Raw is persisted
BEFORE parsing so every failure downstream is recoverable by reprocessing
(never re-crawling).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.eventbus import Event, EventBus
from core.ids import new_trace_id
from core.logging import get_logger
from extraction import CandidateRecord
from ingestion import RawRef

from .base import BaseCollector, CollectorContext

log = get_logger("collectors.runtime")


@dataclass
class CollectResult:
    raw_refs: list[RawRef] = field(default_factory=list)
    candidates: list[CandidateRecord] = field(default_factory=list)
    fetched: int = 0
    skipped_dedupe: int = 0
    errors: int = 0


class CollectorRuntime:
    def __init__(self, collector: BaseCollector, ctx: CollectorContext, bus: EventBus):
        # ``collector`` is the plugin; ``ctx`` carries the injected handles.
        self.collector = collector
        self.ctx = ctx
        self.bus = bus
        self._seen_hashes: set[str] = set()

    def run(self) -> CollectResult:
        result = CollectResult()
        for task in self.collector.plan(self.ctx):
            try:
                self._process(task, result)
            except Exception as exc:  # noqa: BLE001 - runtime isolates poison tasks
                result.errors += 1
                log.warning(
                    "task failed",
                    extra={"context": {"url": task.url, "err": str(exc)}},
                )
        return result

    def _process(self, task, result: CollectResult) -> None:
        response = self.ctx.fetch.get(task.url, headers=task.headers)
        if not response.ok:
            result.errors += 1
            log.info(
                "non-ok fetch",
                extra={"context": {"url": task.url, "status": response.status}},
            )
            return

        # Content-level dedupe: unchanged bytes skip parse (spec 03 §4.4).
        if response.content_hash in self._seen_hashes:
            result.skipped_dedupe += 1
            return
        self._seen_hashes.add(response.content_hash)

        # Persist RAW before parsing (invariant: never lose raw).
        ref = self.ctx.raw_store.put(
            self.ctx.source_slug, response.body, response.fetched_at
        )
        result.raw_refs.append(ref)
        result.fetched += 1
        self.bus.publish(
            Event(
                type="raw.fetched",
                payload={"url": task.url, "raw_key": ref.key, "content_hash": ref.content_hash},
                idempotency_key=ref.content_hash,
                producer=f"{self.collector.collector_slug}@{self.collector.version}",
                trace_id=self.ctx.trace_id,
            )
        )

        doc = self.collector.parse(response, self.ctx)
        candidates = self.collector.normalize(doc, self.ctx)
        for cand in candidates:
            result.candidates.append(cand)
            topic = "signals.candidate" if cand.kind == "signal" else "entities.candidate"
            subtype = cand.entity_type or cand.signal_type
            self.bus.publish(
                Event(
                    type=topic,
                    payload=cand.model_dump(mode="json"),
                    idempotency_key=f"{ref.content_hash}:{cand.evidence.claim_type}:{subtype}",
                    producer=f"{self.collector.collector_slug}@{self.collector.version}",
                    trace_id=self.ctx.trace_id,
                )
            )


def make_context(
    source_slug: str, fetch, raw_store, trace_id: str | None = None
) -> CollectorContext:
    return CollectorContext(
        source_slug=source_slug,
        fetch=fetch,
        raw_store=raw_store,
        trace_id=trace_id or new_trace_id(),
    )
