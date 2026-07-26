"""In-memory event bus adapter.

Synchronous, deduplicating on ``idempotency_key`` (effectively-once, NFR-3).
For tests and single-process local runs only; production uses a durable log.
"""

from __future__ import annotations

from collections import defaultdict

from .base import Event, EventHandler


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._seen: set[str] = set()
        self.published: list[Event] = []

    def publish(self, event: Event) -> None:
        # Idempotent: a replayed event with the same key is a no-op (invariant I3).
        dedupe_key = f"{event.type}:{event.idempotency_key}"
        if dedupe_key in self._seen:
            return
        self._seen.add(dedupe_key)
        self.published.append(event)
        for handler in self._handlers.get(event.type, []):
            handler(event)

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)

    def reset(self) -> None:
        self._handlers.clear()
        self._seen.clear()
        self.published.clear()
