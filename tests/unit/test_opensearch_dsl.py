"""OpenSearch projection builders (pure; no cluster). The client wrapper is
exercised in staging against a live cluster."""

from search.intent import parse_query
from search.opensearch import (
    build_query,
    company_index_mapping,
    company_to_doc,
    opportunity_index_mapping,
)


def _filter_terms(dsl):
    return {list(f["term"].keys())[0]: list(f["term"].values())[0]
            for f in dsl["query"]["bool"].get("filter", [])}


def test_hiring_query_compiles_to_term_filter():
    dsl = build_query(parse_query("companies hiring SDR"))
    assert _filter_terms(dsl).get("hiring_departments") == "Sales"
    assert dsl["sort"][0] == {"opportunity_score": "desc"}


def test_tech_and_axis_filters():
    tech = _filter_terms(build_query(parse_query("companies using HubSpot")))
    assert tech["technologies"] == "hubspot"
    axis = _filter_terms(build_query(parse_query("companies looking for CRM")))
    assert axis["intent_axes"] == "crm"


def test_free_text_is_multi_match():
    dsl = build_query(parse_query("acme robotics"))
    should = dsl["query"]["bool"]["should"]
    assert should and "multi_match" in should[0]


def test_empty_query_is_match_all():
    dsl = build_query(parse_query(""))
    assert dsl["query"]["bool"]["must"] == [{"match_all": {}}]


def test_mappings_have_expected_fields():
    cm = company_index_mapping()["mappings"]["properties"]
    assert "hiring_departments" in cm and cm["intent_vector"]["type"] == "knn_vector"
    om = opportunity_index_mapping()["mappings"]["properties"]
    assert om["tier"]["type"] == "keyword"


class _Ent:
    def __init__(self):
        self.id = 1
        self.display_name = "Acme"
        self.attributes = {"name": "Acme", "primary_domain": "acme.com", "industry": "SaaS"}


class _Sig:
    def __init__(self, stype, axis, dept=None, tech=None):
        self.signal_type = stype
        self.intent_axis = axis
        self.attributes = {"department": dept, "tech": tech}


class _Opp:
    def __init__(self, tier, score):
        self.tier = tier
        self.opportunity_score = score


def test_company_to_doc_projection():
    doc = company_to_doc(
        _Ent(),
        [_Sig("hiring", "hiring", dept="Sales"), _Sig("tech_adoption", "hubspot", tech="hubspot")],
        [_Opp("silver", 0.4), _Opp("gold", 0.7)],
        ["raised a round", "evaluating a CRM"],
    )
    assert doc["domain"] == "acme.com"
    assert doc["hiring_departments"] == ["Sales"]
    assert doc["technologies"] == ["hubspot"]
    assert doc["tier"] == "gold" and doc["opportunity_score"] == 0.7
    assert "CRM" in doc["evidence_text"]
