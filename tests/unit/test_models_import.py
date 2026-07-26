"""Sanity checks on the ORM metadata (no DB required).

Verifies the schema invariants that are expressible in SQLAlchemy metadata:
evidence-backed edges/signals and the key uniqueness constraints (spec 01).
"""

from storage import (
    Base,
    models,  # noqa: F401  (registers tables on Base.metadata)
)


def test_core_tables_registered():
    tables = set(Base.metadata.tables)
    for t in (
        "entity",
        "entity_source",
        "evidence",
        "edge",
        "signal",
        "opportunity",
        "opportunity_transition",
        "score",
        "company",
        "person",
    ):
        assert t in tables


def test_edge_has_evidence_and_confidence_checks():
    edge = Base.metadata.tables["edge"]
    check_names = {c.name for c in edge.constraints if c.name}
    assert "ck_edge_evidence" in check_names  # cardinality(evidence_ids) > 0  (invariant I2)
    assert "ck_edge_conf" in check_names


def test_opportunity_unique_company_template():
    opp = Base.metadata.tables["opportunity"]
    uniques = {
        tuple(sorted(c.columns.keys()))
        for c in opp.constraints
        if c.name == "uq_opp_company_template"
    }
    assert ("company_entity_id", "template_id") in uniques


def test_entity_unique_type_key():
    ent = Base.metadata.tables["entity"]
    names = {c.name for c in ent.constraints if c.name}
    assert "uq_entity_type_key" in names
