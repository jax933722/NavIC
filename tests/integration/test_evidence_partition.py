"""evidence partitioning on Postgres: routing, the composite-PK get() path, and
the idempotent partition-maintenance runner (spec 01 §6)."""

from __future__ import annotations

from datetime import UTC, datetime


def test_evidence_is_partitioned_routes_and_get_works(db_session):
    from sqlalchemy import text

    from maintenance import partition_name
    from storage.sql_repositories import SqlEvidenceRepo

    strat = db_session.execute(text(
        "SELECT partstrat FROM pg_partitioned_table pt "
        "JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'evidence'"
    )).scalar()
    assert strat == "r"

    repo = SqlEvidenceRepo(db_session)
    ev = repo.add(url="https://acme.com/x", claim_type="signal.funding_raised",
                  snippet="raised a round", confidence=0.7, content_hash="deadbeef")
    db_session.commit()

    # get() by id must still work despite the composite PK.
    fetched = repo.get(ev.id)
    assert fetched is not None and fetched.url == "https://acme.com/x"

    # The row routed to this month's partition.
    part = partition_name("evidence", datetime.now(UTC))
    n = db_session.execute(text(f"SELECT count(*) FROM {part}")).scalar()
    assert n == 1


def test_partition_maintenance_creates_upcoming_and_is_idempotent(db_session):
    from sqlalchemy import text

    from maintenance import run_partition_maintenance

    # ahead=6 reaches months the migration did not pre-create.
    ensured = run_partition_maintenance(db_session, ahead=6)
    assert any(name.startswith("evidence_") for name in ensured)
    assert any(name.startswith("timeline_event_") for name in ensured)

    # Idempotent: a second run raises nothing (CREATE ... IF NOT EXISTS).
    run_partition_maintenance(db_session, ahead=6)

    # The parents remain partitioned with more child partitions than the baseline.
    count = db_session.execute(text(
        "SELECT count(*) FROM pg_inherits i JOIN pg_class p ON p.oid = i.inhparent "
        "WHERE p.relname = 'evidence'"
    )).scalar()
    assert count >= 5  # DEFAULT + monthly
