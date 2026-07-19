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
