"""Exercises the OpenSearch adapter through the REAL opensearch-py client over
real HTTP against a stub that emulates the OpenSearch REST API. This verifies the
adapter wiring end-to-end — index creation with our mapping, document indexing,
and issuing our query DSL — without a Lucene cluster (the sandbox can't run one).
The search engine itself is covered by the DSL unit tests + staging."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("opensearchpy")

_RECORer: dict = {"requests": []}


class _OSHandler(BaseHTTPRequestHandler):
    def _body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw) if raw else None

    def _send(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Elastic-Product", "OpenSearch")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_HEAD(self):
        # index-exists check: report "does not exist" so create is exercised.
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        self._send(200, {"version": {"distribution": "opensearch", "number": "2.13.0"},
                         "tagline": "The OpenSearch Project"})

    def do_PUT(self):
        body = self._body()
        _RECORer["requests"].append(("PUT", self.path, body))
        self._send(200, {"acknowledged": True, "result": "created", "_id": "1"})

    def do_POST(self):
        body = self._body()
        _RECORer["requests"].append(("POST", self.path, body))
        if "/_search" in self.path:
            self._send(200, {"hits": {"hits": [
                {"_source": {"entity_id": 10, "name": "Acme", "domain": "acme.com"}}
            ]}})
        else:
            self._send(201, {"result": "created", "_id": "1"})

    def log_message(self, *a):
        pass


@pytest.fixture
def os_stub():
    _RECORer["requests"].clear()
    srv = HTTPServer(("127.0.0.1", 0), _OSHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def test_adapter_creates_index_indexes_and_queries(os_stub):
    from search.intent import parse_query
    from search.opensearch import OpenSearchIndex, company_index_mapping

    idx = OpenSearchIndex(os_stub, index="companies")

    # 1) ensure_index sends our mapping via PUT /companies
    idx.ensure_index(company_index_mapping())
    puts = [r for r in _RECORer["requests"] if r[0] == "PUT" and r[1].rstrip("/") == "/companies"]
    assert puts, "adapter should PUT /companies to create the index"
    assert "hiring_departments" in puts[0][2]["mappings"]["properties"]

    # 2) index a document
    idx.index_document(10, {"entity_id": 10, "name": "Acme", "domain": "acme.com"})
    assert any("/companies/_doc/10" in r[1] for r in _RECORer["requests"])

    # 3) our query DSL is issued and hits are parsed back
    results = idx.search(parse_query("companies hiring SDR"), limit=25)
    search_req = next(r for r in _RECORer["requests"] if "/_search" in r[1])
    filters = search_req[2]["query"]["bool"]["filter"]
    assert {"term": {"hiring_departments": "Sales"}} in filters
    assert results and results[0]["domain"] == "acme.com"
