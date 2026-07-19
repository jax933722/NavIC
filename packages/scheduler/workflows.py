"""Temporal workflow + activity definitions (blueprint §19).

Wraps a single collector run as a durable workflow: retries, timeouts, heartbeats,
and history come from Temporal. The activity delegates to the same
CollectorRuntime the InProcessExecutor uses, so behaviour is identical — only the
execution substrate differs. Imports of ``temporalio`` are lazy/guarded so this
module loads without the SDK installed (the domain layer stays dependency-free);
a worker process installs temporalio and hosts these definitions.
"""

from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - exercised only where the SDK is installed
    from temporalio import activity, workflow
    from temporalio.common import RetryPolicy

    _HAS_TEMPORAL = True
except ImportError:  # pragma: no cover
    _HAS_TEMPORAL = False


@dataclass
class CrawlInput:
    collector_slug: str
    seed_key: str


def run_crawl_activity_impl(collector_slug: str, seed_key: str) -> int:
    """The actual work: run one collector over one seed. Reused by the activity
    and callable directly in tests. Returns the candidate count."""
    import collectors.sources  # noqa: F401
    from collectors import CollectorRuntime
    from collectors.registry import get_collector
    from collectors.runtime import make_context
    from core.eventbus import InMemoryEventBus
    from ingestion import HttpFetchClient, InMemoryRawStore

    collector = get_collector(collector_slug)
    collector._seeds = [seed_key]
    ctx = make_context(collector.source_slug, HttpFetchClient(), InMemoryRawStore())
    return len(CollectorRuntime(collector, ctx, InMemoryEventBus()).run().candidates)


if _HAS_TEMPORAL:  # pragma: no cover - requires the Temporal SDK + server

    @activity.defn(name="run_crawl")
    async def run_crawl_activity(collector_slug: str, seed_key: str) -> int:
        return run_crawl_activity_impl(collector_slug, seed_key)

    @workflow.defn
    class CrawlWorkflow:
        @workflow.run
        async def run(self, collector_slug: str, seed_key: str) -> int:
            from datetime import timedelta

            return await workflow.execute_activity(
                run_crawl_activity,
                args=[collector_slug, seed_key],
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=RetryPolicy(maximum_attempts=5),
            )

else:  # SDK not installed: expose a stub so imports/type refs resolve.

    class CrawlWorkflow:  # type: ignore[no-redef]
        async def run(self, collector_slug: str, seed_key: str) -> int:
            return run_crawl_activity_impl(collector_slug, seed_key)
