"""Proves timeline_event is really partitioned on Postgres and that inserts via
the ORM repo route to the correct monthly partition (spec 01 §6)."""

from __future__ import annotations

from datetime import UTC, datetime


def test_timeline_event_is_partitioned_and_routes(db_session):
    from sqlalchemy import text

    from maintenance import partition_name
    from storage.sql_repositories import SqlEntityRepo, SqlTimelineRepo

    # Parent must be a partitioned table.
    strat = db_session.execute(text(
        "SELECT partstrat FROM pg_partitioned_table pt "
        "JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'timeline_event'"
    )).scalar()
    assert strat == "r"  # RANGE

    # Insert a timeline event for a company (FK) and confirm it lands in this
    # month's partition specifically.
    company = SqlEntityRepo(db_session).create_blank("company")
    SqlTimelineRepo(db_session).add(
        company_entity_id=company.id, event_type="funding_raised",
        summary="raised a round", signal_id=None, evidence_ids=[],
    )
    db_session.commit()

    part = partition_name("timeline_event", datetime.now(UTC))
    n = db_session.execute(text(f"SELECT count(*) FROM {part}")).scalar()
    assert n == 1, f"row should route to {part}"
