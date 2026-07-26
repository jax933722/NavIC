from search import parse_query


def test_hiring_role():
    intent = parse_query("companies hiring SDR")
    assert intent.hiring_department == "Sales"
    assert "hiring:Sales" in intent.filters_found


def test_using_tech():
    intent = parse_query("companies using HubSpot")
    assert intent.tech == "hubspot"
    assert intent.is_structured()


def test_looking_for_axis():
    intent = parse_query("companies looking for CRM")
    assert intent.looking_for_axis == "crm"


def test_people_discussing():
    intent = parse_query("people discussing deliverability")
    assert intent.target == "person"
    assert intent.discussing_axis == "deliverability"


def test_switching_competitors():
    intent = parse_query("companies switching CRM")
    assert intent.signal_type == "tech_churn"


def test_free_text_fallback():
    intent = parse_query("acme robotics")
    assert not intent.is_structured()
    assert intent.free_text == "acme robotics"
