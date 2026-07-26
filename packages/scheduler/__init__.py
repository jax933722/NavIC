"""scheduler — adaptive crawl planning (spec 03 / blueprint §19).

Decides *what* to crawl and *when*: per-source cadence with an adaptive rate so
high-value (hot) targets are re-crawled more often, prioritised by value×staleness.
This module is the planner; a durable executor (Temporal, blueprint §19) invokes
``plan`` on a tick and runs the returned tasks. In-memory + testable here.
"""

from .executor import Executor, InProcessExecutor, TemporalExecutor, TickResult
from .planner import CrawlTarget, Scheduler

__all__ = [
    "CrawlTarget",
    "Scheduler",
    "Executor",
    "InProcessExecutor",
    "TemporalExecutor",
    "TickResult",
]
