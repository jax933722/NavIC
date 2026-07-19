"""raw_document: partitioning + content-addressed indexing (spec 01 §3.5)."""

from __future__ import annotations

from datetime import UTC, datetime


def test_raw_document_partitioned_routes_and_dedupes(db_session):
    from sqlalchemy import text

    from maintenance import partition_name
    from storage.sql_repositories import SqlRawDocumentRepo

    strat = db_session.execute(text(
        "SELECT partstrat FROM pg_partitioned_table pt "
        "JOIN pg_class c ON c.oid = pt.partrelid WHERE c.relname = 'raw_document'"
    )).scalar()
    assert strat == "r"

    repo = SqlRawDocumentRepo(db_session)
    ref = repo.add(source_id=1, collector_id=1, url="https://acme.com/",
                   s3_key="raw/company_web/2026/07/abc", content_hash="abc",
                   content_type="text/html", http_status=200)
    # Content-addressed: same hash indexes once.
    again = repo.add(source_id=1, collector_id=1, url="https://acme.com/",
                     s3_key="raw/company_web/2026/07/abc", content_hash="abc")
    db_session.commit()
    assert ref.id == again.id

    assert repo.get_by_hash("abc") is not None

    part = partition_name("raw_document", datetime.now(UTC))
    n = db_session.execute(text(f"SELECT count(*) FROM {part}")).scalar()
    assert n == 1
