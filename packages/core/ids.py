"""Identity helpers.

- ``content_hash`` gives the sha256 used for raw dedupe and pipeline idempotency
  keys (invariant I3 / NFR-3).
- ``new_trace_id`` mints the correlation id propagated through the event
  envelope and logs (docs/ARCHITECTURE.md §23).
"""

from __future__ import annotations

import hashlib
import uuid


def content_hash(body: bytes) -> str:
    """Stable sha256 hex digest of raw bytes."""
    return hashlib.sha256(body).hexdigest()


def content_hash_str(text: str) -> str:
    return content_hash(text.encode("utf-8"))


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_event_id() -> str:
    return uuid.uuid4().hex
