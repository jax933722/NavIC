"""API tests (spec 06). Seeds state via the orchestrator with a stub fetch
client, then exercises the read endpoints through Starlette's TestClient."""

from __future__ import annotations

import pytest
from apps.api.main import app
from apps.api.repos import InMemoryProvider
from fastapi.testclient import TestClient

from ingestion import StubFetchClient
from pipeline import ingest_company_web_urls

HOMEPAGE = """
<html><head><title>Acme Robotics</title>
<meta property="og:site_name" content="Acme Robotics"/></head>
<body><a href="/careers">Careers</a> we're hiring!</body></html>
"""
URL = "https://www.acme.com/"


@pytest.fixture
def client():
    provider = InMemoryProvider()
    app.state.provider = provider  # fresh in-memory repos per test
    with provider.bundle() as r:
        ingest_company_web_urls(
            [URL],
            pipeline=r.pipeline,
            fetch=StubFetchClient({URL: (200, "text/html", HOMEPAGE)}),
        )
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_list_opportunities_bronze(client):
    r = client.get("/v1/opportunities", params={"tier": "bronze"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 1
    card = body["data"][0]
    assert card["tier"] == "bronze"
    assert card["company"]["domain"] == "acme.com"
    assert card["opportunity_score"] > 0
    assert card["evidence_refs"], "card must embed evidence (principle A2)"


def test_get_opportunity_and_evidence(client):
    card = client.get("/v1/opportunities", params={"tier": "all"}).json()["data"][0]
    opp = client.get(f"/v1/opportunities/{card['id']}").json()
    assert opp["id"] == card["id"]

    ev_id = opp["evidence_refs"][0]["id"]
    ev = client.get(f"/v1/evidence/{ev_id}").json()
    assert ev["url"] == URL
    assert ev["claim_type"]


def test_get_company(client):
    card = client.get("/v1/opportunities").json()["data"][0]
    company_id = card["company"]["id"]
    detail = client.get(f"/v1/companies/{company_id}").json()
    assert detail["domain"] == "acme.com"
    assert detail["signals"] >= 1
    assert len(detail["opportunities"]) == 1


def test_not_found(client):
    assert client.get("/v1/opportunities/99999").status_code == 404
    assert client.get("/v1/evidence/99999").status_code == 404
    assert client.get("/v1/companies/99999").status_code == 404


def test_search_hiring(client):
    r = client.get("/v1/search", params={"q": "companies hiring"})
    assert r.status_code == 200
    body = r.json()
    assert "structured_filters" in body["interpreted"]
    # The seeded Acme fixture has a hiring signal.
    assert any(item["name"] == "Acme Robotics" for item in body["data"])
