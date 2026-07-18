from datetime import UTC, datetime, timedelta

from entities import Observation, project

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def test_higher_trust_wins():
    obs = [
        Observation({"name": "Acme Incorporated"}, "community", evidence_id=1, observed_at=NOW),
        Observation({"name": "Acme"}, "official", evidence_id=2, observed_at=NOW),
    ]
    proj = project(obs, now=NOW)
    assert proj["name"] == "Acme"
    assert 2 in proj["name__provenance"]["chosen_evidence_ids"]


def test_multiplicity_breaks_ties_within_same_trust():
    obs = [
        Observation({"industry": "SaaS"}, "news", evidence_id=1, observed_at=NOW),
        Observation({"industry": "SaaS"}, "news", evidence_id=2, observed_at=NOW),
        Observation({"industry": "Fintech"}, "news", evidence_id=3, observed_at=NOW),
    ]
    proj = project(obs, now=NOW)
    assert proj["industry"] == "SaaS"


def test_volatile_field_prefers_recent():
    obs = [
        Observation({"current_role": "SDR"}, "official", evidence_id=1,
                    observed_at=NOW - timedelta(days=300)),
        Observation({"current_role": "VP Sales"}, "official", evidence_id=2, observed_at=NOW),
    ]
    proj = project(obs, now=NOW)
    assert proj["current_role"] == "VP Sales"


def test_alternatives_are_recorded():
    obs = [
        Observation({"name": "Acme"}, "official", evidence_id=1, observed_at=NOW),
        Observation({"name": "Acme Corp"}, "community", evidence_id=2, observed_at=NOW),
    ]
    proj = project(obs, now=NOW)
    prov = proj["name__provenance"]
    assert prov["chosen_value"] == "Acme"
    assert any(alt["value"] == "Acme Corp" for alt in prov["alternatives"])
