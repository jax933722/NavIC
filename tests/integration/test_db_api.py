"""DB-backed API: the same endpoints served from Postgres via SqlProvider.

Proves the API is datastore-agnostic — identical endpoint code, Postgres behind
it. Skips when no database is configured."""

from __future__ import annotations

from apps.api.main import app
from apps.api.repos import SqlProvider
from fastapi.testclient import TestClient

from ingestion import StubFetchClient
from pipeline import ingest_company_web_urls

HOMEPAGE = """
<html><head><title>Acme Robotics</title>
<meta property="og:site_name" content="Acme Robotics"/></head>
<body>We raised a Series A. Evaluating a Salesforce alternative for our CRM.
Careers we're hiring SDRs across sales. Leadership: Jane Roe — VP of Sales.</body></html>
"""
URL = "https://acme.com/"


def test_api_reads_from_postgres(db_session):  # db_session fixture ensures a clean DB + skip
    provider = SqlProvider()
    app.state.provider = provider

    # Seed through the DB-backed pipeline.
    with provider.bundle() as r:
        ingest_company_web_urls(
            [URL], pipeline=r.pipeline,
            fetch=StubFetchClient({URL: (200, "text/html", HOMEPAGE)}),
        )

    client = TestClient(app)
    board = client.get("/v1/opportunities", params={"tier": "all"}).json()
    assert board["data"], "API should read persisted opportunities from Postgres"
    names = {d["company"]["name"] for d in board["data"]}
    assert "Acme Robotics" in names

    # Search endpoint over the SQL repos.
    hits = client.get("/v1/search", params={"q": "companies looking for CRM"}).json()
    assert any(x["name"] == "Acme Robotics" for x in hits["data"])
