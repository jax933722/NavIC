"""Graph mirror (spec 02 §3.2).

The `edge` table is the source of truth; Apache AGE is a derived query surface for
openCypher traversal. A ``GraphMirror`` keeps AGE in sync with entity/edge writes.
``NullMirror`` is the default (edges are served relationally today); ``AgeGraphMirror``
issues idempotent Cypher MERGEs. The Cypher builders are pure and unit-tested; the
adapter runs against a Postgres with the AGE extension loaded (staging).
"""

from __future__ import annotations

from typing import Protocol

GRAPH_NAME = "oip"


def _esc(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def node_merge_cypher(entity_type: str, entity_id: int, label: str | None) -> str:
    """Idempotent MERGE of a vertex keyed on entity_id, carrying its label.

    RETURN is required: AGE only applies an updating clause when the statement
    returns a row. Setting a property whose key is the MERGE key persists on
    create, so a single MERGE+SET is fine for vertices.
    """
    return (
        f"MERGE (n:{entity_type} {{entity_id: {int(entity_id)}}}) "
        f"SET n.label = '{_esc(label or '')}' RETURN id(n)"
    )


def edge_merge_cypher(edge_type: str, src_id: int, dst_id: int) -> str:
    """Idempotent MERGE of a relationship between two labelled-by-key vertices."""
    return (
        f"MATCH (a {{entity_id: {int(src_id)}}}), (b {{entity_id: {int(dst_id)}}}) "
        f"MERGE (a)-[r:{edge_type}]->(b) RETURN id(r)"
    )


def edge_set_confidence_cypher(edge_type: str, src_id: int, dst_id: int, confidence: float) -> str:
    """Set an edge property in a separate statement.

    AGE (1.5) does not apply a SET to a relationship that MERGE creates in the
    same statement, and lacks ON CREATE SET; so confidence is set on the existing
    edge in a follow-up MATCH ... SET.
    """
    return (
        f"MATCH ({{entity_id: {int(src_id)}}})-[r:{edge_type}]->({{entity_id: {int(dst_id)}}}) "
        f"SET r.confidence = {float(confidence)} RETURN id(r)"
    )


def wrap_age(cypher: str, columns: str = "(v agtype)") -> str:
    """Wrap a Cypher statement in the AGE SQL calling convention."""
    return f"SELECT * FROM cypher('{GRAPH_NAME}', $$ {cypher} $$) AS {columns}"


class GraphMirror(Protocol):
    def upsert_node(self, entity_type: str, entity_id: int, label: str | None) -> None: ...
    def upsert_edge(self, edge_type: str, src_id: int, dst_id: int, confidence: float) -> None: ...


class NullMirror:
    """Default: no-op. Edges are served relationally; AGE mirroring is opt-in."""

    def upsert_node(self, entity_type, entity_id, label) -> None:  # noqa: D401
        return None

    def upsert_edge(self, edge_type, src_id, dst_id, confidence) -> None:
        return None


class AgeGraphMirror:
    """Mirrors into Apache AGE via the SQL/Cypher bridge. Requires the AGE
    extension (`CREATE EXTENSION age; SELECT create_graph('oip')`). Lazily uses a
    connection so the domain layer has no hard AGE dependency."""

    def __init__(self, conn):
        self._conn = conn  # a DBAPI/SQLAlchemy connection with AGE loaded

    def _exec(self, cypher: str) -> None:
        from sqlalchemy import text

        self._conn.execute(text('LOAD \'age\''))
        self._conn.execute(text('SET search_path = ag_catalog, "$user", public'))
        self._conn.execute(text(wrap_age(cypher)))

    def upsert_node(self, entity_type: str, entity_id: int, label: str | None) -> None:
        self._exec(node_merge_cypher(entity_type, entity_id, label))

    def upsert_edge(self, edge_type: str, src_id: int, dst_id: int, confidence: float) -> None:
        # Two statements: MERGE the edge, then SET its property on the existing edge
        # (AGE quirk — see edge_set_confidence_cypher).
        self._exec(edge_merge_cypher(edge_type, src_id, dst_id))
        self._exec(edge_set_confidence_cypher(edge_type, src_id, dst_id, confidence))
