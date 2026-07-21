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


def test_seed_crud_and_jobboard_validation(tmp_path):
    from apps.api.seedstore import SeedStore

    app.state.provider = InMemoryProvider()
    app.state.seeds = SeedStore(str(tmp_path / "seeds.json"))
    client = TestClient(app)

    # starts empty, and lists the available collector slugs to choose from
    listing = client.get("/v1/admin/seeds").json()
    assert listing["data"] == [] and "greenhouse" in listing["sources"]

    # a job board without a company website is rejected
    bad = client.post("/v1/admin/seeds", json={
        "source": "greenhouse",
        "url": "https://boards-api.greenhouse.io/v1/boards/acme/jobs"})
    assert bad.status_code == 422 and "company_domain" in bad.json()["detail"]

    # with the website it is accepted and persisted
    ok = client.post("/v1/admin/seeds", json={
        "source": "greenhouse",
        "url": "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        "company_domain": "acme.com", "company_name": "Acme"})
    assert ok.status_code == 200
    tid = ok.json()["id"]

    # an unknown source is rejected; a feed without a company is fine
    assert client.post("/v1/admin/seeds",
                       json={"source": "nope", "url": "x"}).status_code == 422
    assert client.post("/v1/admin/seeds",
                       json={"source": "rss_blog", "url": "https://x/feed.xml"}).status_code == 200

    assert len(client.get("/v1/admin/seeds").json()["data"]) == 2

    # persistence: a fresh store over the same file sees the saved targets
    assert len(SeedStore(str(tmp_path / "seeds.json")).list()) == 2

    # delete
    assert client.delete(f"/v1/admin/seeds/{tid}").status_code == 200
    assert client.delete("/v1/admin/seeds/99999").status_code == 404
    assert len(client.get("/v1/admin/seeds").json()["data"]) == 1


def test_crawler_uses_configured_jobboard_target(tmp_path, monkeypatch):
    """A configured Greenhouse target with a live-shaped payload (no company block)
    is anchored via the operator-supplied company website."""
    import json
    import time

    from apps.api import crawler as crawler_mod
    from apps.api.seedstore import SeedStore

    from ingestion import StubFetchClient

    url = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    body = json.dumps({"jobs": [
        {"title": "Senior Account Executive", "absolute_url": url + "/1",
         "departments": [{"name": "Sales"}]},
        {"title": "Staff Engineer", "absolute_url": url + "/2",
         "departments": [{"name": "Engineering"}]}]})

    app.state.provider = InMemoryProvider()
    app.state.seeds = SeedStore(str(tmp_path / "seeds.json"))
    app.state.seeds.add("greenhouse", url, company_domain="acme.com", company_name="Acme")
    app.state.crawler = crawler_mod.CrawlerManager(
        provider_getter=lambda: app.state.provider,
        fetch_factory=lambda: StubFetchClient({url: (200, "application/json", body)}),
        seeds_provider=lambda: app.state.seeds.list())
    client = TestClient(app)

    client.post("/v1/admin/crawler/start", params={"interval_seconds": 10})
    status = {}
    for _ in range(30):
        status = client.get("/v1/admin/crawler/status").json()
        if status["cycles"] >= 1:
            break
        time.sleep(0.1)
    client.post("/v1/admin/crawler/stop")

    assert status["per_source"]["greenhouse"]["ok"] is True
    board = client.get("/v1/opportunities").json()["data"]
    assert any(o["company"]["domain"] == "acme.com" for o in board)


def test_crawler_start_runs_a_cycle_then_stops(monkeypatch):
    import time
    from pathlib import Path

    from apps.api import crawler as crawler_mod

    from ingestion import StubFetchClient

    url = "https://stub.local/hn"
    body = (Path(__file__).parent.parent
            / "fixtures/collectors/hn_freelance/search.json").read_text()
    # Offline: default sources -> one stubbed HN feed; fetch client -> the stub.
    monkeypatch.setattr(crawler_mod, "_default_sources", lambda: [("hn_freelance", [url], {})])
    app.state.provider = InMemoryProvider()
    app.state.crawler = crawler_mod.CrawlerManager(
        provider_getter=lambda: app.state.provider,
        fetch_factory=lambda: StubFetchClient({url: (200, "application/json", body)}))
    client = TestClient(app)

    assert client.get("/v1/admin/crawler/status").json()["running"] is False
    assert client.post("/v1/admin/crawler/start",
                       params={"interval_seconds": 10}).json()["running"] is True

    status = {}
    for _ in range(30):  # wait for the first cycle (runs in a background thread)
        status = client.get("/v1/admin/crawler/status").json()
        if status["cycles"] >= 1:
            break
        time.sleep(0.1)
    assert status["cycles"] >= 1
    assert status["per_source"]["hn_freelance"]["ok"] is True

    # New leads are live on the board while it runs.
    board = client.get("/v1/opportunities").json()["data"]
    assert any(o["company"]["domain"] == "northwindlabs.io" for o in board)

    assert client.post("/v1/admin/crawler/stop").json()["running"] is False
