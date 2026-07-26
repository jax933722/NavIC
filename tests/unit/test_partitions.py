from datetime import UTC, datetime

from maintenance import (
    create_partition_sql,
    monthly_partition_bounds,
    next_partitions,
    partition_name,
)


def test_bounds_span_the_month():
    start, end, suffix = monthly_partition_bounds(datetime(2026, 7, 19, tzinfo=UTC))
    assert start == datetime(2026, 7, 1, tzinfo=UTC)
    assert end == datetime(2026, 8, 1, tzinfo=UTC)
    assert suffix == "2026_07"


def test_year_boundary():
    start, end, _ = monthly_partition_bounds(datetime(2026, 12, 15, tzinfo=UTC))
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)


def test_partition_name_and_sql():
    dt = datetime(2026, 7, 19, tzinfo=UTC)
    assert partition_name("evidence", dt) == "evidence_2026_07"
    sql = create_partition_sql("evidence", dt)
    assert "PARTITION OF evidence" in sql
    assert "FROM ('2026-07-01') TO ('2026-08-01')" in sql


def test_next_partitions_covers_current_plus_ahead():
    parts = next_partitions(now=datetime(2026, 7, 19, tzinfo=UTC), ahead=2)
    months = {dt.strftime("%Y_%m") for _, dt in parts}
    assert months == {"2026_07", "2026_08", "2026_09"}
    parents = {p for p, _ in parts}
    assert "evidence" in parents and "timeline_event" in parents
