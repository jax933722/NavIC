"""Fetch client (spec 03 §2.1, §4.1).

Network I/O with retry/backoff and a content hash computed on every response.
``RawResponse.content_hash`` is set by the client so downstream stages get a
stable idempotency key (invariant I3). A ``StubFetchClient`` backs tests.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from core.ids import content_hash
from core.logging import get_logger

log = get_logger("ingestion.fetch")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RawResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes
    content_type: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def content_hash(self) -> str:
        return content_hash(self.body)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class FetchClient(Protocol):
    def get(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse: ...


class HttpFetchClient:
    """Production client (httpx) with bounded retry + exponential backoff (spec 03 §4.1)."""

    def __init__(
        self, *, timeout: float = 20.0, max_attempts: int = 5, user_agent: str | None = None
    ):
        import httpx  # imported lazily so the domain layer needn't depend on it

        self._httpx = httpx
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent or "NavicBot/0.1 (+https://navic.local/bot)"},
        )
        self._max_attempts = max_attempts

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        attempt = 0
        while True:
            attempt += 1
            try:
                r = self._client.get(url, headers=dict(headers or {}))
            except self._httpx.HTTPError as exc:
                if attempt >= self._max_attempts:
                    raise
                self._backoff(attempt)
                log.warning(
                    "fetch retry",
                    extra={"context": {"url": url, "attempt": attempt, "err": str(exc)}},
                )
                continue
            if r.status_code in _RETRYABLE_STATUS and attempt < self._max_attempts:
                self._backoff(attempt, retry_after=r.headers.get("Retry-After"))
                continue
            return RawResponse(
                url=str(r.url),
                status=r.status_code,
                headers=dict(r.headers),
                body=r.content,
                content_type=r.headers.get("content-type", "application/octet-stream"),
            )

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None = None) -> None:
        if retry_after and retry_after.isdigit():
            time.sleep(min(60, int(retry_after)))
            return
        time.sleep(min(60.0, 2 ** (attempt - 1)))


class StubFetchClient:
    """Deterministic fetch client for tests: serves canned responses by URL."""

    def __init__(self, responses: dict[str, tuple[int, str, str]]):
        # url -> (status, content_type, body)
        self._responses = responses
        self.calls: list[str] = []

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> RawResponse:
        self.calls.append(url)
        status, content_type, body = self._responses.get(url, (404, "text/html", ""))
        return RawResponse(
            url=url,
            status=status,
            headers={"content-type": content_type},
            body=body.encode("utf-8"),
            content_type=content_type,
        )
