"""Proves the monthly-partition DDL actually works against Postgres: create a
partitioned table, attach a month partition via the helper, insert, verify
routing. Skips without a database."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest


@pytest.fixture
def raw_conn():
    if not os.environ.get("NAVIC_DATABASE_URL"):
        pytest.skip("NAVIC_DATABASE_URL not set")
    try:
        from sqlalchemy import text

        from storage.db import get_engine

        conn = get_engine().connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")
    conn.execute(text("DROP TABLE IF EXISTS _part_demo CASCADE"))
    conn.commit()
    yield conn
    conn.execute(text("DROP TABLE IF EXISTS _part_demo CASCADE"))
    conn.commit()
    conn.close()


def test_monthly_partition_ddl_routes_rows(raw_conn):
    from sqlalchemy import text

    from maintenance import create_partition_sql, partition_name

    raw_conn.execute(text(
        "CREATE TABLE _part_demo (id bigint, observed_at timestamptz NOT NULL) "
        "PARTITION BY RANGE (observed_at)"
    ))
    dt = datetime(2026, 7, 15, tzinfo=UTC)
    raw_conn.execute(text(create_partition_sql("_part_demo", dt)))
    raw_conn.execute(text(
        "INSERT INTO _part_demo VALUES (1, '2026-07-10T00:00:00Z')"
    ))
    raw_conn.commit()

    # The row landed in the July partition specifically.
    part = partition_name("_part_demo", dt)
    n = raw_conn.execute(text(f"SELECT count(*) FROM {part}")).scalar()
    assert n == 1
