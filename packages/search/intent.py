"""Query intent parsing (spec 16.3).

Compiles natural phrasing into structured filters where confident, else leaves
free text for full-text matching. Deterministic and transparent — the parsed
intent is echoed back to the operator ("interpreted as ...").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from signals.taxonomy import DEPARTMENT_BY_ROLE, PAIN_AXES

# Map a phrase after "looking for / in-market for / need" to an intent axis.
_AXIS_SYNONYMS = {
    "crm": "crm",
    "deliverability": "deliverability",
    "email deliverability": "deliverability",
    "analytics": "analytics",
    "bi": "analytics",
    "enrichment": "data_enrichment",
    "data enrichment": "data_enrichment",
    "outbound": "outbound",
    "sales engagement": "outbound",
}

# Known technologies recognised in "using X" / "mentioning X".
_KNOWN_TECH = {
    "hubspot", "salesforce", "pipedrive", "marketo", "pardot", "outreach",
    "apollo", "zoominfo", "segment", "snowflake", "looker", "tableau",
    "sendgrid", "mailgun", "postmark", "intercom", "zendesk", "stripe",
}


@dataclass
class QueryIntent:
    raw: str
    target: str = "company"                     # 'company' | 'person'
    hiring_department: str | None = None
    tech: str | None = None
    looking_for_axis: str | None = None
    signal_type: str | None = None
    discussing_axis: str | None = None          # for people
    free_text: str = ""
    filters_found: list[str] = field(default_factory=list)

    def is_structured(self) -> bool:
        return bool(self.filters_found)


def _find_department(phrase: str) -> str | None:
    for keyword, dept in DEPARTMENT_BY_ROLE.items():
        if keyword in phrase:
            return dept
    return None


def _find_axis(phrase: str) -> str | None:
    for syn, axis in _AXIS_SYNONYMS.items():
        if syn in phrase:
            return axis
    # Fall back to pain-axis vocab.
    for axis, phrases in PAIN_AXES.items():
        if any(p in phrase for p in phrases):
            return axis
    return None


def parse_query(query: str) -> QueryIntent:
    q = query.strip().lower()
    intent = QueryIntent(raw=query)

    if q.startswith("people") or "people " in q or q.startswith("who "):
        intent.target = "person"

    if re.search(r"\bhiring\b", q):
        m = re.search(r"hiring\s+([a-z /]+)", q)
        dept = _find_department(m.group(1)) if m else None
        dept = dept or _find_department(q)
        if dept:
            intent.hiring_department = dept
            intent.signal_type = "hiring"
            intent.filters_found.append(f"hiring:{dept}")
        else:
            # Bare "hiring" with no recognised role -> match any hiring signal.
            intent.signal_type = "hiring"
            intent.filters_found.append("signal:hiring")

    m = re.search(r"\b(using|use|on)\s+([a-z0-9.]+)", q)
    if m and m.group(2) in _KNOWN_TECH:
        intent.tech = m.group(2)
        intent.filters_found.append(f"tech:{intent.tech}")

    m = re.search(r"(looking for|in-market for|in market for|need|want|evaluating)\s+([a-z /]+)", q)
    if m:
        axis = _find_axis(m.group(2))
        if axis:
            intent.looking_for_axis = axis
            intent.signal_type = intent.signal_type or "pain_mention"
            intent.filters_found.append(f"looking_for:{axis}")

    if "switching" in q or "migrating" in q or "churn" in q:
        intent.signal_type = "tech_churn"
        intent.filters_found.append("signal:tech_churn")

    if re.search(r"\b(raised|funding|funded|series [a-e]|seed)\b", q):
        intent.signal_type = "funding_raised"
        intent.filters_found.append("signal:funding_raised")

    if intent.target == "person":
        m = re.search(r"(discussing|talking about|mention\w*)\s+([a-z /]+)", q)
        if m:
            axis = _find_axis(m.group(2))
            if axis:
                intent.discussing_axis = axis
                intent.filters_found.append(f"discussing:{axis}")

    m = re.search(r"mention\w*\s+([a-z0-9.]+)", q)
    if m and m.group(1) in _KNOWN_TECH and not intent.tech:
        intent.tech = m.group(1)
        intent.filters_found.append(f"mentions:{intent.tech}")

    if not intent.is_structured():
        intent.free_text = q
    return intent
