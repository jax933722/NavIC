"""Adaptive crawl planner (spec 03 §19).

Priority = value × staleness. High-value targets get a shorter *effective*
cadence (crawled more often), so freshness is concentrated where it pays. A
target is due when its age exceeds its effective cadence; the due list is
returned most-overdue-highest-value first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class CrawlTarget:
    seed_key: str                       # host / feed url / crawl scope
    collector_slug: str
    base_cadence: timedelta             # default period for this source
    value_score: float = 0.0            # 0..1, hotness (recent signals / tier)
    last_crawled: datetime | None = None
    priority: float = field(default=0.0, init=False)

    def effective_cadence(self) -> timedelta:
        # Hot targets crawl up to ~2x more often; value in [0,1].
        factor = 1.0 + max(0.0, min(1.0, self.value_score))
        return self.base_cadence / factor

    def age(self, now: datetime) -> timedelta:
        if self.last_crawled is None:
            return timedelta(days=3650)  # never crawled -> maximally overdue
        lc = self.last_crawled
        if lc.tzinfo is None:
            lc = lc.replace(tzinfo=UTC)
        return now - lc

    def is_due(self, now: datetime) -> bool:
        return self.age(now) >= self.effective_cadence()

    def compute_priority(self, now: datetime) -> float:
        cadence_s = max(1.0, self.effective_cadence().total_seconds())
        staleness_ratio = self.age(now).total_seconds() / cadence_s
        # value weights the staleness; +0.1 floor so brand-new targets still rank.
        self.priority = (0.1 + self.value_score) * staleness_ratio
        return self.priority


class Scheduler:
    def plan(self, targets: list[CrawlTarget], now: datetime | None = None,
             limit: int | None = None) -> list[CrawlTarget]:
        now = now or datetime.now(UTC)
        due = [t for t in targets if t.is_due(now)]
        for t in due:
            t.compute_priority(now)
        due.sort(key=lambda t: t.priority, reverse=True)
        return due[:limit] if limit else due

    def mark_crawled(self, target: CrawlTarget, now: datetime | None = None,
                     value_score: float | None = None) -> None:
        target.last_crawled = now or datetime.now(UTC)
        if value_score is not None:
            target.value_score = value_score
