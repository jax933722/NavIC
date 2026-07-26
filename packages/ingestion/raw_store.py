"""Raw store (spec 03 §4.5, blueprint invariant: never delete raw).

Persists raw bytes immutably, addressed by content hash, BEFORE any parsing.
``InMemoryRawStore`` / ``LocalFileRawStore`` back tests and local runs; the S3
adapter (MinIO/production) implements the same ``RawStore`` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from core.ids import content_hash


@dataclass(frozen=True)
class RawRef:
    """A pointer to stored raw bytes (mirrors the raw_document index row)."""

    key: str
    content_hash: str
    size: int
    fetched_at: datetime


def _key_for(source_slug: str, hash_hex: str, when: datetime) -> str:
    return f"raw/{source_slug}/{when:%Y}/{when:%m}/{hash_hex}"


class RawStore(Protocol):
    def put(self, source_slug: str, body: bytes, when: datetime | None = None) -> RawRef: ...

    def get(self, key: str) -> bytes | None: ...


class InMemoryRawStore:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put(self, source_slug: str, body: bytes, when: datetime | None = None) -> RawRef:
        when = when or datetime.now(UTC)
        h = content_hash(body)
        key = _key_for(source_slug, h, when)
        # Content-addressed: identical bytes collapse to one object (dedupe).
        self._data.setdefault(key, body)
        return RawRef(key=key, content_hash=h, size=len(body), fetched_at=when)

    def get(self, key: str) -> bytes | None:
        return self._data.get(key)


class LocalFileRawStore:
    """Filesystem-backed raw store for local development."""

    def __init__(self, root: str | Path = ".data/raw"):
        self._root = Path(root)

    def put(self, source_slug: str, body: bytes, when: datetime | None = None) -> RawRef:
        when = when or datetime.now(UTC)
        h = content_hash(body)
        key = _key_for(source_slug, h, when)
        path = self._root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():  # immutable + content-addressed
            path.write_bytes(body)
        return RawRef(key=key, content_hash=h, size=len(body), fetched_at=when)

    def get(self, key: str) -> bytes | None:
        path = self._root / key
        return path.read_bytes() if path.exists() else None
