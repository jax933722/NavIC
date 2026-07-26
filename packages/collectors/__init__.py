"""collectors — pluggable source collectors + the runtime that drives them.

Adding a source is a new module under ``sources/`` plus ``@register`` — zero
core changes (spec 03 §1, §6). The runtime owns cross-cutting concerns; the
collector implements only source-specific logic.
"""

from .base import BaseCollector, Capabilities, CollectorContext, FetchTask
from .registry import REGISTRY, get_collector, register
from .runtime import CollectorRuntime, CollectResult

__all__ = [
    "BaseCollector",
    "Capabilities",
    "CollectorContext",
    "FetchTask",
    "REGISTRY",
    "register",
    "get_collector",
    "CollectorRuntime",
    "CollectResult",
]
