"""Shared fixtures for DB-backed integration tests.

Tests that need Postgres use the ``db_session`` fixture, which connects to
NAVIC_DATABASE_URL and SKIPS the test if no database is reachable — so the suite
stays green on machines without a DB, while running for real in CI/dev where one
is provisioned. Each test runs in a transaction that is rolled back at the end.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def db_session():
    if not os.environ.get("NAVIC_DATABASE_URL"):
        pytest.skip("NAVIC_DATABASE_URL not set — DB integration test skipped")
    try:
        from sqlalchemy import text

        from storage.db import get_engine, get_sessionmaker

        get_engine().connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")

    session = get_sessionmaker()()
    # Reset search_path in case a pooled connection was left on the AGE catalog
    # by a prior test (test isolation for the shared engine pool).
    session.execute(text("SET search_path = public"))
    # Clean slate for deterministic assertions (order respects FKs).
    for table in (
        "opportunity_transition", "opportunity", "signal", "entity_merge",
        "resolution_review", "blocking_key", "entity_source", "evidence",
        "raw_document", "timeline_event", "company", "person", "edge", "score", "entity",
    ):
        session.execute(text(f"TRUNCATE {table} RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
