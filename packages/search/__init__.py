"""search — query understanding + retrieval (spec 16).

M5 serves structured + full-text search over the canonical repositories (the
OpenSearch projection is the scale path). The intent parser compiles the
operator's phrasing into filters; the service executes and ranks with evidence.
"""

from .intent import QueryIntent, parse_query
from .service import SearchResult, SearchService

__all__ = ["QueryIntent", "parse_query", "SearchService", "SearchResult"]
