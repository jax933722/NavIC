"""AGE mirror Cypher generation (pure). The adapter runs against AGE in staging."""

from graph import GraphBuilder, NullMirror
from graph.mirror import edge_merge_cypher, node_merge_cypher, wrap_age
from storage.repositories import InMemoryEdgeRepo


def test_node_merge_cypher_is_idempotent_shape():
    c = node_merge_cypher("person", 42, "VP of Sales")
    assert "MERGE (n:person {entity_id: 42})" in c
    assert "label: 'VP of Sales'" in c


def test_edge_merge_cypher():
    c = edge_merge_cypher("works_at", 2, 1, 0.7)
    assert "MATCH (a {entity_id: 2}), (b {entity_id: 1})" in c
    assert "MERGE (a)-[r:works_at]->(b)" in c
    assert "r.confidence = 0.7" in c


def test_cypher_escaping():
    c = node_merge_cypher("company", 5, "O'Brien & Co")
    assert "O\\'Brien" in c  # single quote escaped for the Cypher string literal


def test_wrap_age_sql_bridge():
    sql = wrap_age("MATCH (n) RETURN n")
    assert sql.startswith("SELECT * FROM cypher('oip'")
    assert "$$ MATCH (n) RETURN n $$" in sql


class _RecordingMirror:
    def __init__(self):
        self.nodes = []
        self.edges = []

    def upsert_node(self, t, i, label):
        self.nodes.append((t, i))

    def upsert_edge(self, et, s, d, c):
        self.edges.append((et, s, d))


def test_graph_builder_calls_mirror():
    mirror = _RecordingMirror()
    gb = GraphBuilder(InMemoryEdgeRepo(), mirror=mirror)
    gb.works_at(person_id=2, company_id=1, role="VP of Sales", evidence_ids=[9])
    assert ("person", 2) in mirror.nodes and ("company", 1) in mirror.nodes
    assert ("works_at", 2, 1) in mirror.edges


def test_default_mirror_is_noop():
    gb = GraphBuilder(InMemoryEdgeRepo())  # NullMirror by default
    edge = gb.works_at(person_id=2, company_id=1, role="CTO", evidence_ids=[1])
    assert edge.edge_type == "works_at"  # no error, edge still written
    assert isinstance(gb._mirror, NullMirror)
