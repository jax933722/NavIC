"""Per-opportunity workflow status — turns the board into a working queue.

An opportunity is `active` (default), `contacted`, or `dismissed`. Kept in a small
JSON file (not the core schema) so it works the same for the in-memory and Postgres
backends and survives restarts. Keyed by opportunity id, which is deterministic for
a given dataset.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

_DEFAULT_PATH = os.environ.get("NAVIC_STATUS_PATH", "./.data/status.json")
VALID = {"active", "contacted", "dismissed"}


class StatusStore:
    def __init__(self, path: str | None = None):
        self._path = Path(path or _DEFAULT_PATH)
        self._lock = threading.Lock()
        self._by_id: dict[int, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        self._by_id = {int(k): v for k, v in data.items()}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({str(k): v for k, v in self._by_id.items()}, indent=2))

    def status_of(self, opportunity_id: int) -> str:
        with self._lock:
            return self._by_id.get(opportunity_id, {}).get("status", "active")

    def entry_of(self, opportunity_id: int) -> dict | None:
        with self._lock:
            return self._by_id.get(opportunity_id)

    def set(self, opportunity_id: int, status: str, note: str | None = None) -> dict:
        with self._lock:
            if status == "active":
                # Returning to the queue clears the record entirely.
                self._by_id.pop(opportunity_id, None)
                self._save()
                return {"status": "active"}
            entry = {"status": status, "note": (note or "").strip() or None,
                     "updated_at": datetime.now(UTC).isoformat()}
            self._by_id[opportunity_id] = entry
            self._save()
            return entry
