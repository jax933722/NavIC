"""Person extraction from team/about pages (spec 04 / M4).

Deterministic: JSON-LD Person entries plus a "Name — Role" text pattern where the
role contains a leadership keyword. Each person becomes an evidence-backed
candidate carrying the company apex as context (person matching is context-first).
"""

from __future__ import annotations

import re

from parsing import ParsedDocument

from .evidence import CandidateRecord, EvidenceDraft, build_candidate

_LEADERSHIP = (
    "ceo", "cto", "coo", "cfo", "cmo", "cro", "founder", "co-founder", "president",
    "vp", "vice president", "head", "director", "chief", "lead", "manager",
)

# "Jane Roe, VP of Sales" / "Jane Roe — Head of Growth" / "Jane Roe - Director of Marketing"
# Role stops at a sentence boundary (no '.') so consecutive people don't merge.
_NAME_ROLE_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[,–—-]\s*"
    r"([A-Z][A-Za-z&/ ]{2,50}?)(?=[.\n;•|]|\s+[A-Z][a-z]+\s+[A-Z][a-z]+\s*[,–—-]|$)",
)


def _is_role(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in _LEADERSHIP)


def extract_people(doc: ParsedDocument, apex: str) -> list[CandidateRecord]:
    people: dict[str, CandidateRecord] = {}

    # 1) JSON-LD Person (from schema.org markup).
    structured = doc.structured or {}
    for person in _iter_jsonld_people(structured):
        name = person.get("name")
        role = person.get("jobTitle") or person.get("worksFor", {}).get("jobTitle")
        if name:
            _add(people, name, role, doc.url, apex, confidence=0.9)

    # 2) "Name — Role" text patterns.
    for match in _NAME_ROLE_RE.finditer(doc.text):
        name, role = match.group(1).strip(), match.group(2).strip()
        if _is_role(role):
            _add(people, name, role, doc.url, apex, confidence=0.6,
                 snippet=match.group(0)[:120])

    return list(people.values())


def _add(people, name, role, url, apex, *, confidence, snippet=None) -> None:
    key = name.lower()
    if key in people:
        return
    people[key] = build_candidate(
        kind="entity", entity_type="person",
        attributes={
            "full_name": name, "name": name, "display_name": name,
            "current_role": role, "company_domain": apex, "company_apex": apex,
        },
        evidence=EvidenceDraft(
            url=url, claim_type="person.role",
            snippet=snippet or f"{name} — {role}" if role else name, confidence=confidence,
        ),
        blocking_hints={"name": name, "company_apex": apex},
    )


def _iter_jsonld_people(data):
    if isinstance(data, dict):
        if data.get("@type") == "Person":
            yield data
        for value in data.values():
            yield from _iter_jsonld_people(value)
    elif isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_people(item)
