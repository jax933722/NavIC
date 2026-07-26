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


def test_solicitation_detected_with_service_category():
    # The exact shape of a public "who can I hire" buying request.
    text = ("Can anyone recommend a website designer who is great at creating "
            "on-brand Shopify product pages that convert?")
    cands = detect_signals(text, "https://linkedin/posts/x", "buyer.com")
    sol = next(c for c in cands if c.signal_type == SignalType.SOLICITATION)
    assert sol.attributes["intent_axis"] == "web_design"
    assert sol.attributes["department"] == "Marketing"
    assert sol.attributes["weak"] is False  # explicit ask -> qualifying, high strength
    assert sol.attributes["strength"] >= 0.85


def test_solicitation_variants():
    for text, axis in [
        ("Looking for a great SEO agency to grow organic traffic", "seo"),
        ("Who should I use for Google Ads / paid media?", "paid_ads"),
        ("Need a good copywriter for our content marketing", "content"),
    ]:
        cands = detect_signals(text, "https://x/", "x.com")
        assert axis in {c.attributes.get("intent_axis") for c in cands
                        if c.signal_type == SignalType.SOLICITATION}


def test_solicitation_categorizes_security_and_mobile():
    sec = detect_signals("Looking for a WordPress Malware Removal Expert to clean a hacked site",
                         "https://x/", "x.com")
    assert any(c.attributes["intent_axis"] == "security"
               for c in sec if c.signal_type == SignalType.SOLICITATION)
    mob = detect_signals("Looking for an experienced Flutter/App Developer for iOS and Android",
                         "https://x/", "x.com")
    assert any(c.attributes["intent_axis"] == "mobile_app"
               for c in mob if c.signal_type == SignalType.SOLICITATION)


def test_solicitation_extracts_qualifying_detail():
    text = ("Looking for a Web Developer / agency / freelancer to build an e-commerce website. "
            "Timeline: 30 days. Budget: $2000 USD.")
    sol = next(c for c in detect_signals(text, "https://x/", "x.com")
               if c.signal_type == SignalType.SOLICITATION)
    assert sol.attributes["budget"] == "$2000"
    assert sol.attributes["timeline"] == "30 days"
    assert "agency" in sol.attributes["engagement"] and "freelance" in sol.attributes["engagement"]

    mern = next(c for c in detect_signals(
        "Looking for a MERN developer. MongoDB, Express, React & Node.js. Remote.",
        "https://x/", "x.com") if c.signal_type == SignalType.SOLICITATION)
    assert mern.attributes["remote"] is True
    assert "mern" in mern.attributes["stack"] and "mongodb" in mern.attributes["stack"]


def test_solicitation_ignores_non_buying_requests():
    # A request phrase with no service category must NOT create a solicitation.
    for text in [
        "Looking for feedback on my new blog post",
        "I'm looking for a new role in marketing",
        "Can anyone recommend a good book on leadership?",
    ]:
        cands = detect_signals(text, "https://x/", "x.com")
        assert SignalType.SOLICITATION not in _types(cands)
