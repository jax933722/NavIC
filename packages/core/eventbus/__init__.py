"""Event bus abstraction.

The pipeline talks to a thin ``EventBus`` interface so the durable backbone can
evolve (Redis Streams -> NATS -> Kafka) without touching producers/consumers
(docs/ARCHITECTURE.md §5.3). The in-memory adapter backs unit tests and local runs.
"""

from __future__ import annotations

from .base import Event, EventBus, EventHandler
from .memory import InMemoryEventBus

__all__ = ["Event", "EventBus", "EventHandler", "InMemoryEventBus"]
