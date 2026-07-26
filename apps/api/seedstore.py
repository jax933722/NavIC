"""Operator seed list — the specific targets the crawler should pull from.

A target is one source to watch: a collector slug + a URL, plus (for job boards) the
company's own website, because provider APIs return their ATS-hosted URL, not the
company domain we anchor leads on. Persisted as JSON so it survives restarts.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

_DEFAULT_PATH = os.environ.get("NAVIC_SEEDS_PATH", "./.data/seeds.json")


@dataclass
class Target:
    id: int
    source: str
    url: str
    company_domain: str | None = None
    company_name: str | None = None


class SeedStore:
    def __init__(self, path: str | None = None):
        self._path = Path(path or _DEFAULT_PATH)
        self._lock = threading.Lock()
        self._targets: list[Target] = []
        self._next_id = 1
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        self._targets = [Target(**t) for t in data.get("targets", [])]
        self._next_id = max((t.id for t in self._targets), default=0) + 1

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"targets": [asdict(t) for t in self._targets]}, indent=2))

    def list(self) -> list[Target]:
        with self._lock:
            return list(self._targets)

    def add(self, source: str, url: str, company_domain: str | None = None,
            company_name: str | None = None) -> Target:
        with self._lock:
            target = Target(id=self._next_id, source=source, url=url.strip(),
                            company_domain=(company_domain or "").strip() or None,
                            company_name=(company_name or "").strip() or None)
            self._targets.append(target)
            self._next_id += 1
            self._save()
            return target

    def remove(self, target_id: int) -> bool:
        with self._lock:
            before = len(self._targets)
            self._targets = [t for t in self._targets if t.id != target_id]
            if len(self._targets) != before:
                self._save()
                return True
            return False
