"""Operator admin endpoints: collectors listing + ER review queue adjudication."""

from __future__ import annotations

import pytest
from apps.api.main import app
from apps.api.repos import InMemoryProvider
from fastapi.testclient import TestClient

from extraction import EvidenceDraft, build_candidate


def _company(name, domain):
    return build_candidate(
        kind="entity", entity_type="company",
        attributes={"name": name, "display_name": name, "primary_domain": domain},
        evidence=EvidenceDraft(url=f"https://{domain}/", claim_type="company.domain",
                               confidence=0.9),
    )


@pytest.fixture
def client_with_review():
    provider = InMemoryProvider()
    app.state.provider = provider
    with provider.bundle() as r:
        # Two identically-named companies on different domains -> borderline -> review.
        r.pipeline.ingest(
            [_company("Northwind Traders", "northwind-traders.com")], content_hash="a"
        )
        r.pipeline.ingest([_company("Northwind Traders", "northwind.io")], content_hash="b")
    return TestClient(app)


def test_list_collectors():
    app.state.provider = InMemoryProvider()
    body = TestClient(app).get("/v1/admin/collectors").json()
    slugs = {c["collector"] for c in body["data"]}
    assert {"company_web", "rss_blog", "github_org", "hackernews"} <= slugs


def test_review_queue_and_merge(client_with_review):
    client = client_with_review
    reviews = client.get("/v1/admin/resolution/review").json()["data"]
    assert reviews, "a borderline pair should be queued for review"
    review = reviews[0]
    assert review["left"]["name"] and review["right"]["name"]
    assert 0.6 <= review["match_prob"] < 0.9

    # Adjudicate: merge.
    resp = client.post(f"/v1/admin/resolution/{review['id']}/decide", params={"decision": "merge"})
    assert resp.status_code == 200

    # The queue is now empty (the pair was decided).
    after = client.get("/v1/admin/resolution/review").json()["data"]
    assert len(after) < len(reviews)


def test_decide_rejects_bad_decision(client_with_review):
    assert client_with_review.post(
        "/v1/admin/resolution/1/decide", params={"decision": "bogus"}
    ).status_code == 422


def test_capture_turns_a_pasted_post_into_a_gold_opportunity():
    app.state.provider = InMemoryProvider()
    client = TestClient(app)
    resp = client.post("/v1/admin/capture", json={
        "text": ("Can anyone recommend a website designer for on-brand Shopify product "
                 "pages? Budget around $2000, need it in 30 days."),
        "company_domain": "brightbrew.co",
        "company_name": "BrightBrew",
        "author_name": "Priya Nair",
        "author_role": "Head of Marketing",
        "source_url": "https://www.linkedin.com/posts/priya-nair_shopify",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "solicitation" in body["detected_signals"]
    gold = [o for o in body["opportunities"] if o["tier"] == "gold"]
    assert gold, "author + role + company + service request should qualify Gold"
    opp = gold[0]
    assert opp["person_name"] == "Priya Nair"
    assert opp["qualifiers"]["service"] == "web_design"
    assert opp["qualifiers"]["budget"] == "$2000"
    assert opp["qualifiers"]["timeline"] == "30 days"


def test_capture_requires_a_company_domain():
    app.state.provider = InMemoryProvider()
    client = TestClient(app)
    assert client.post("/v1/admin/capture",
                       json={"text": "hi", "company_domain": ""}).status_code == 422


def test_import_csv_creates_opportunities_with_contact():
    app.state.provider = InMemoryProvider()
    client = TestClient(app)
    csv = (
        b"name,company domain,requirement,email\n"
        b"Priya Nair,brightbrew.co,Looking for a Shopify web designer budget $2000,"
        b"priya@brightbrew.co\n"
        b"Jane Roe,acme-io.com,Looking for an SEO agency,\n"
        b",,no domain here,\n"
    )
    resp = client.post("/v1/admin/import", files={"file": ("leads.csv", csv, "text/csv")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == 3 and body["imported"] == 2 and body["skipped"] == 1
    assert body["row_errors"], "the domain-less row should be reported"

    # The imported contact (name + email) rides on the opportunity card.
    board = client.get("/v1/opportunities").json()["data"]
    bright = next(o for o in board if o["company"]["domain"] == "brightbrew.co")
    assert bright["contact"]["name"] == "Priya Nair"
    assert bright["contact"]["email"] == "priya@brightbrew.co"
    assert bright["qualifiers"]["budget"] == "$2000"


def test_import_xlsx_is_supported():
    import io

    import openpyxl

    app.state.provider = InMemoryProvider()
    client = TestClient(app)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Company Domain", "Requirement", "Email"])
    ws.append(["Sam Okafor", "https://umbrella.io/careers",
               "Need a Flutter developer for iOS and Android", "sam@umbrella.io"])
    buf = io.BytesIO()
    wb.save(buf)
    resp = client.post(
        "/v1/admin/import",
        files={"file": ("leads.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] == 1
    board = client.get("/v1/opportunities").json()["data"]
    # Domain parsed from a full URL; mobile_app category detected.
    umb = next(o for o in board if o["company"]["domain"] == "umbrella.io")
    assert umb["contact"]["email"] == "sam@umbrella.io"


def test_import_rejects_empty_file():
    app.state.provider = InMemoryProvider()
    client = TestClient(app)
    assert client.post("/v1/admin/import",
                       files={"file": ("empty.csv", b"", "text/csv")}).status_code == 422
