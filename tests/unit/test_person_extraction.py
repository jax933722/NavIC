from extraction import extract_people
from parsing import ParsedDocument


def test_extracts_name_role_pattern():
    doc = ParsedDocument(
        url="https://acme.com/team",
        text="Our leadership: Jane Roe — VP of Sales. John Doe - Head of Growth.",
    )
    people = extract_people(doc, "acme.com")
    names = {p.attributes["full_name"] for p in people}
    assert "Jane Roe" in names and "John Doe" in names
    jane = next(p for p in people if p.attributes["full_name"] == "Jane Roe")
    assert "sales" in jane.attributes["current_role"].lower()
    assert jane.attributes["company_apex"] == "acme.com"
    assert jane.evidence.claim_type == "person.role"


def test_extracts_jsonld_person():
    doc = ParsedDocument(
        url="https://acme.com/about",
        text="",
        structured={"@type": "Person", "name": "Ada Lovelace", "jobTitle": "CTO"},
    )
    people = extract_people(doc, "acme.com")
    assert people and people[0].attributes["full_name"] == "Ada Lovelace"


def test_ignores_non_role_text():
    doc = ParsedDocument(url="https://acme.com/", text="New York — a great city to visit.")
    assert extract_people(doc, "acme.com") == []
