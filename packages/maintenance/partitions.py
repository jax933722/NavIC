"""Monthly RANGE partition management (spec 01 §6).

Generates the bounds, names, and DDL to pre-create monthly partitions for the
time-partitioned tables, and lists the partitions that should exist ahead of now.
Retention is tiering, never DROP for raw/evidence (blueprint §8): old partitions
are DETACHed for cold storage, not dropped.
"""

from __future__ import annotations

from datetime import UTC, datetime

# Tables partitioned by month (parent -> partition column).
PARTITIONED_TABLES: dict[str, str] = {
    "evidence": "observed_at",
    "raw_document": "fetched_at",
    "timeline_event": "occurred_at",
    "score_history": "computed_at",
}


def _first_of_month(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, 1, tzinfo=dt.tzinfo or UTC)


def _next_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo or UTC)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=dt.tzinfo or UTC)


def monthly_partition_bounds(dt: datetime) -> tuple[datetime, datetime, str]:
    """Return (inclusive_start, exclusive_end, suffix) for dt's month."""
    start = _first_of_month(dt)
    end = _next_month(start)
    return start, end, f"{start:%Y_%m}"


def partition_name(parent: str, dt: datetime) -> str:
    _, _, suffix = monthly_partition_bounds(dt)
    return f"{parent}_{suffix}"


def create_partition_sql(parent: str, dt: datetime) -> str:
    start, end, _ = monthly_partition_bounds(dt)
    name = partition_name(parent, dt)
    return (
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {parent} "
        f"FOR VALUES FROM ('{start:%Y-%m-%d}') TO ('{end:%Y-%m-%d}')"
    )


def next_partitions(now: datetime | None = None, ahead: int = 3) -> list[tuple[str, datetime]]:
    """The (parent, month) partitions that should exist from this month forward."""
    now = now or datetime.now(UTC)
    out: list[tuple[str, datetime]] = []
    cursor = _first_of_month(now)
    for _ in range(ahead + 1):  # current month + `ahead` future months
        for parent in PARTITIONED_TABLES:
            out.append((parent, cursor))
        cursor = _next_month(cursor)
    return out


def _partitioned_parents(conn) -> set[str]:
    from sqlalchemy import text

    rows = conn.execute(text(
        "SELECT c.relname FROM pg_partitioned_table pt "
        "JOIN pg_class c ON c.oid = pt.partrelid"
    )).scalars().all()
    return set(rows)


def run_partition_maintenance(conn, now: datetime | None = None, ahead: int = 3) -> list[str]:
    """Idempotently create upcoming monthly partitions for every partitioned parent
    that exists. Safe to run on every maintenance tick (CREATE ... IF NOT EXISTS).
    Returns the partition names ensured. Retention (DETACH of cold months) is a
    separate, deliberate policy — this only creates, never drops."""
    from sqlalchemy import text

    existing_parents = _partitioned_parents(conn)
    ensured: list[str] = []
    for parent, dt in next_partitions(now=now, ahead=ahead):
        if parent not in existing_parents:
            continue
        conn.execute(text(create_partition_sql(parent, dt)))
        ensured.append(partition_name(parent, dt))
    return ensured
