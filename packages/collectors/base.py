"""Collector contract (spec 03 §2).

The collector implements plan/fetch/parse/normalize; the runtime (runtime.py)
injects fetch client, raw store, and the event bus, and owns retry, dedupe,
raw persistence, emission, and logging.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from extraction import CandidateRecord
from ingestion import FetchClient, RawResponse, RawStore
from parsing import ParsedDocument


@dataclass(frozen=True)
class Capabilities:
    supports_incremental: bool = False
    needs_browser: bool = False
    auth_kind: str | None = None
    politeness_class: str = "standard"
    max_concurrency: int = 4


@dataclass(frozen=True)
class FetchTask:
    url: str
    seed_key: str | None = None
    priority: int = 0
    render: bool = False
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class CollectorContext:
    """Runtime-provided handles + per-run state."""

    source_slug: str
    fetch: FetchClient
    raw_store: RawStore
    trace_id: str


@runtime_checkable
class BaseCollector(Protocol):
    source_slug: str
    collector_slug: str
    version: str
    capabilities: Capabilities

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]: ...

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument: ...

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]: ...
