from signals import SignalType, detect_signals


def _types(cands):
    return {c.signal_type for c in cands}


def test_funding_detected():
    text = "Today we announced we raised a $12M Series A round led by Acme Ventures."
    cands = detect_signals(text, "https://x/", "x.com")
    assert SignalType.FUNDING_RAISED in _types(cands)


def test_hiring_with_department_inference():
    text = "We're hiring! Open roles: Senior SDR and Sales Development Rep."
    cands = detect_signals(text, "https://x/", "x.com")
    hiring = next(c for c in cands if c.signal_type == SignalType.HIRING)
    assert hiring.attributes["department"] == "Sales"
    assert hiring.attributes["weak"] is False  # department found -> qualifying


def test_pain_mention_axis():
    text = "We are frustrated with our CRM and evaluating a Salesforce alternative."
    cands = detect_signals(text, "https://x/", "x.com")
    pain = [c for c in cands if c.signal_type == SignalType.PAIN_MENTION]
    assert pain and pain[0].attributes["intent_axis"] == "crm"


def test_tech_adoption_detected():
    text = "Our stack runs on HubSpot and Snowflake."
    cands = detect_signals(text, "https://x/", "x.com")
    techs = {c.attributes.get("tech") for c in cands if c.signal_type == SignalType.TECH_ADOPTION}
    assert "hubspot" in techs and "snowflake" in techs


def test_tech_churn_detected():
    text = "We are migrating from Salesforce to a leaner tool."
    cands = detect_signals(text, "https://x/", "x.com")
    assert SignalType.TECH_CHURN in _types(cands)


def test_every_signal_has_evidence():
    text = "We raised a seed round. We're hiring SDRs. Migrating off HubSpot."
    cands = detect_signals(text, "https://x/", "x.com")
    assert cands
    assert all(c.evidence and c.evidence.url and c.evidence.claim_type for c in cands)


def test_no_false_positive_on_plain_text():
    cands = detect_signals("We make really good coffee for offices.", "https://x/", "x.com")
    assert cands == []
