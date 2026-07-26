"""Event envelope + bus protocol.

Envelope matches docs/ARCHITECTURE.md §14.4. Consumers are add-only; schema
evolves via ``schema_version`` bumps and tolerant readers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from core.ids import new_event_id, new_trace_id


@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]
    idempotency_key: str
    schema_version: int = 1
    event_id: str = field(default_factory=new_event_id)
    trace_id: str = field(default_factory=new_trace_id)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    producer: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "type": self.type,
            "schema_version": self.schema_version,
            "occurred_at": self.occurred_at.isoformat(),
            "trace_id": self.trace_id,
            "idempotency_key": self.idempotency_key,
            "producer": self.producer,
            "payload": self.payload,
        }


EventHandler = Callable[[Event], None]


class EventBus(Protocol):
    """Minimal publish/subscribe contract; adapters implement durability."""

    def publish(self, event: Event) -> None: ...

    def subscribe(self, topic: str, handler: EventHandler) -> None: ...
