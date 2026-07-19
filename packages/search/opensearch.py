"""OpenSearch projection + query DSL (spec 16.2).

The canonical store answers search today (packages/search/service.py); at scale
the same queries are served from an OpenSearch projection. This module is that
projection: index mappings, the document shape, and the query-DSL compiler from a
parsed QueryIntent. The pure builders here are unit-tested without a cluster; the
``OpenSearchIndex`` client wrapper lazily imports opensearch-py and is exercised
against a live cluster in staging (not in unit tests).
"""

from __future__ import annotations

from typing import Any

from .intent import QueryIntent

# --------------------------------------------------------------------- mappings
COMPANY_INDEX = "companies"
OPPORTUNITY_INDEX = "opportunities"


def company_index_mapping() -> dict[str, Any]:
    return {
        "mappings": {
            "properties": {
                "entity_id": {"type": "long"},
                "name": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                "domain": {"type": "keyword"},
                "industry": {"type": "keyword"},
                "signal_types": {"type": "keyword"},
                "intent_axes": {"type": "keyword"},
                "hiring_departments": {"type": "keyword"},
                "technologies": {"type": "keyword"},
                "tier": {"type": "keyword"},
                "opportunity_score": {"type": "float"},
                "evidence_text": {"type": "text"},
                "intent_vector": {"type": "knn_vector", "dimension": 1024},
                "updated_at": {"type": "date"},
            }
        }
    }


def opportunity_index_mapping() -> dict[str, Any]:
    return {
        "mappings": {
            "properties": {
                "opportunity_id": {"type": "long"},
                "company_entity_id": {"type": "long"},
                "company_name": {"type": "text", "fields": {"raw": {"type": "keyword"}}},
                "domain": {"type": "keyword"},
                "tier": {"type": "keyword"},
                "thesis": {"type": "text"},
                "department": {"type": "keyword"},
                "decision_maker_role": {"type": "keyword"},
                "opportunity_score": {"type": "float"},
                "updated_at": {"type": "date"},
            }
        }
    }


# --------------------------------------------------------------------- doc shape
def company_to_doc(company, signals, opportunities, evidence_snippets: list[str]) -> dict[str, Any]:
    """Project a company + its rollups into an OpenSearch document."""
    best = max(opportunities, key=lambda o: o.opportunity_score, default=None)
    return {
        "entity_id": company.id,
        "name": company.display_name or company.attributes.get("name"),
        "domain": company.attributes.get("primary_domain"),
        "industry": company.attributes.get("industry"),
        "signal_types": sorted({s.signal_type for s in signals}),
        "intent_axes": sorted({s.intent_axis for s in signals if s.intent_axis}),
        "hiring_departments": sorted(
            {s.attributes.get("department") for s in signals
             if s.signal_type == "hiring" and s.attributes.get("department")}
        ),
        "technologies": sorted(
            {s.attributes.get("tech") for s in signals if s.attributes.get("tech")}
        ),
        "tier": best.tier if best else None,
        "opportunity_score": best.opportunity_score if best else 0.0,
        "evidence_text": " ".join(evidence_snippets),
    }


# --------------------------------------------------------------------- query DSL
def build_query(intent: QueryIntent) -> dict[str, Any]:
    """Compile a parsed intent into an OpenSearch bool query (spec 16.3).

    Structured filters become `filter` clauses (no scoring, cacheable); free text
    becomes a scored multi_match. Ranking is by opportunity_score, then relevance.
    """
    filters: list[dict[str, Any]] = []
    should: list[dict[str, Any]] = []

    if intent.hiring_department:
        filters.append({"term": {"hiring_departments": intent.hiring_department}})
    if intent.tech:
        filters.append({"term": {"technologies": intent.tech}})
    if intent.looking_for_axis:
        filters.append({"term": {"intent_axes": intent.looking_for_axis}})
    if intent.signal_type and not intent.hiring_department and not intent.looking_for_axis:
        filters.append({"term": {"signal_types": intent.signal_type}})
    if intent.free_text:
        should.append({
            "multi_match": {
                "query": intent.free_text,
                "fields": ["name^2", "evidence_text"],
            }
        })

    bool_query: dict[str, Any] = {}
    if filters:
        bool_query["filter"] = filters
    if should:
        bool_query["should"] = should
        bool_query["minimum_should_match"] = 1
    if not bool_query:
        bool_query["must"] = [{"match_all": {}}]

    return {
        "query": {"bool": bool_query},
        "sort": [{"opportunity_score": "desc"}, "_score"],
    }


# --------------------------------------------------------------------- client
class OpenSearchIndex:
    """Thin client wrapper (staging/prod). Lazily imports opensearch-py so the
    domain layer has no hard dependency on it."""

    def __init__(self, url: str, index: str = COMPANY_INDEX):
        from opensearchpy import OpenSearch  # lazy: only needed to actually run

        self._client = OpenSearch(hosts=[url])
        self._index = index

    def ensure_index(self, mapping: dict[str, Any]) -> None:
        # opensearch-py 3.x requires keyword arguments.
        if not self._client.indices.exists(index=self._index):
            self._client.indices.create(index=self._index, body=mapping)

    def index_document(self, doc_id: int, doc: dict[str, Any]) -> None:
        self._client.index(index=self._index, id=doc_id, body=doc)

    def search(self, intent: QueryIntent, limit: int = 25) -> list[dict[str, Any]]:
        res = self._client.search(index=self._index, body=build_query(intent), size=limit)
        return [hit["_source"] for hit in res["hits"]["hits"]]
