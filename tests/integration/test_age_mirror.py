"""Live Apache AGE mirror: write nodes/edges via the adapter, read them back with
openCypher. Skips automatically when AGE isn't installed/loaded."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def age_conn():
    if not os.environ.get("NAVIC_DATABASE_URL"):
        pytest.skip("NAVIC_DATABASE_URL not set")
    try:
        from sqlalchemy import text

        from storage.db import get_engine

        conn = get_engine().connect()
        conn.execute(text("LOAD 'age'"))
        conn.execute(text('SET search_path = ag_catalog, "$user", public'))
        conn.execute(text("SELECT create_graph('oip_test')"))
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Apache AGE not available: {exc}")
    yield conn
    from sqlalchemy import text

    conn.execute(text("SELECT drop_graph('oip_test', true)"))
    conn.commit()
    conn.close()


def test_mirror_writes_and_cypher_reads_back(age_conn, monkeypatch):
    from sqlalchemy import text

    import graph.mirror as mirror_mod
    from graph import AgeGraphMirror

    monkeypatch.setattr(mirror_mod, "GRAPH_NAME", "oip_test")

    mirror = AgeGraphMirror(age_conn)
    mirror.upsert_node("company", 1, "Acme Robotics")
    mirror.upsert_node("person", 2, "Jane Roe")
    mirror.upsert_edge("works_at", 2, 1, 0.7)
    age_conn.commit()

    age_conn.execute(text("LOAD 'age'"))
    age_conn.execute(text('SET search_path = ag_catalog, "$user", public'))
    rows = age_conn.execute(text(
        "SELECT * FROM cypher('oip_test', $$ "
        "MATCH (p:person)-[r:works_at]->(c:company) "
        "RETURN p.label, c.label, r.confidence $$) "
        "AS (person agtype, company agtype, conf agtype)"
    )).fetchall()

    assert rows, "the mirrored works_at path should be traversable in AGE"
    person, company, conf = rows[0]
    assert "Jane Roe" in str(person) and "Acme Robotics" in str(company)
    assert str(conf) == "0.7"  # SET now persists (RETURN added)
