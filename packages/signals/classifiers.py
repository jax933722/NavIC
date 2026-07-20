"""Deterministic signal classifiers (spec 05 §2, blueprint §14.3 tier 1).

Each classifier scans document text/links for a signal pattern and returns an
evidence-backed signal CandidateRecord. Cheap and precise; the LLM extraction
path (spec §14.3) augments these for unstructured prose without changing callers.
"""

from __future__ import annotations

import re

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from parsing import ParsedDocument

from .taxonomy import (
    DEPARTMENT_BY_ROLE,
    PAIN_AXES,
    SERVICE_AXES,
    SERVICE_DEPARTMENT,
    SIGNAL_DEFAULT_STRENGTH,
    SOLICITATION_STACK,
    SignalType,
)

# Known technologies for adoption/churn detection (seed dictionary; expands later).
KNOWN_TECH = {
    "hubspot", "salesforce", "pipedrive", "marketo", "pardot", "outreach",
    "apollo", "zoominfo", "segment", "snowflake", "looker", "tableau",
    "sendgrid", "mailgun", "postmark", "intercom", "zendesk", "stripe",
}

_FUNDING_RE = re.compile(
    r"(raised|secured|closed|announces?)\s+(a\s+)?(\$?\d[\d.,]*\s*(million|billion|m|b|k)?)?\s*"
    r"(seed|series\s+[a-e]|pre-seed|round|funding)",
    re.IGNORECASE,
)
_LAUNCH_RE = re.compile(r"\b(launch(?:ed|ing)?|introducing|announc(?:e|ing)|now available)\b", re.I)
_HIRING_RE = re.compile(
    r"\b(hiring|we're hiring|we are hiring|join our team|open roles?|careers?|now hiring)\b", re.I
)
_CHURN_RE = re.compile(
    r"\b(migrat\w+ (from|off)|switch\w* from|moving (from|away from)|replac\w+)\b", re.I
)
# Public request for a vendor/service recommendation — an explicit in-market ask.
_SOLICITATION_RE = re.compile(
    r"\b(can (?:anyone|someone|somebody) recommend|any (?:recommendations?|recs)\b|"
    r"looking (?:for|to hire)|in search of|on the hunt for|in the market for|"
    r"who (?:should i|do you|would you|can) (?:use|recommend|hire)|"
    r"need (?:help with|(?:a |an )(?:good |great |new |freelance |experienced )?[a-z]{3,})|"
    r"recommendations? for|does anyone know (?:a |an )?good|"
    r"trying to find (?:a |an )?|hire (?:a |an )?(?:freelance |good )?)",
    re.I,
)


def _snippet(text: str, match: re.Match, width: int = 90) -> str:
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    return text[start:end].strip()


def _signal(signal_type: str, apex: str, url: str, snippet: str, *,
            intent_axis: str | None = None, strength: float | None = None,
            department: str | None = None, weak: bool = False,
            extra: dict | None = None) -> CandidateRecord:
    default_strength = SIGNAL_DEFAULT_STRENGTH.get(signal_type, 0.5)
    attrs = {
        "company_domain": apex,
        "strength": strength if strength is not None else default_strength,
        "intent_axis": intent_axis,
        "weak": weak,
    }
    if department:
        attrs["department"] = department
    if extra:
        attrs.update(extra)
    return build_candidate(
        kind="signal", signal_type=str(signal_type),
        attributes=attrs,
        evidence=EvidenceDraft(url=url, claim_type=f"signal.{signal_type}",
                               snippet=snippet[:280], confidence=0.6 if not weak else 0.5),
        blocking_hints={"apex_domain": apex},
    )


def detect_signals(text: str, url: str, apex: str, links_text: str = "") -> list[CandidateRecord]:
    lower = text.lower()
    hay = f"{lower} {links_text.lower()}"
    out: list[CandidateRecord] = []

    m = _FUNDING_RE.search(text)
    if m:
        out.append(_signal(SignalType.FUNDING_RAISED, apex, url, _snippet(text, m),
                           intent_axis="growth"))

    m = _HIRING_RE.search(hay)
    if m:
        dept = _infer_department(hay)
        out.append(_signal(SignalType.HIRING, apex, url, _snippet(hay, m),
                           intent_axis="hiring", department=dept,
                           weak=dept is None, extra={"department": dept} if dept else None))

    for axis, phrases in PAIN_AXES.items():
        for phrase in phrases:
            idx = lower.find(phrase)
            if idx >= 0:
                snip = text[max(0, idx - 40): idx + len(phrase) + 40].strip()
                out.append(_signal(SignalType.PAIN_MENTION, apex, url, snip, intent_axis=axis,
                                   strength=0.75))
                break

    m = _CHURN_RE.search(lower)
    if m:
        tech = _find_tech(lower[m.start(): m.start() + 60])
        out.append(_signal(SignalType.TECH_CHURN, apex, url, _snippet(text, m),
                           intent_axis=tech or "competitor_switch",
                           extra={"tech": tech} if tech else None))

    for tech in _find_all_tech(lower):
        out.append(_signal(SignalType.TECH_ADOPTION, apex, url, f"mentions {tech}",
                           intent_axis=tech, strength=0.55, extra={"tech": tech}))

    m = _LAUNCH_RE.search(lower)
    if m:
        out.append(_signal(SignalType.PRODUCT_LAUNCH, apex, url, _snippet(text, m),
                           intent_axis="scaling", weak=True))

    # Solicitation: an explicit "can anyone recommend a <service>" style ask. We
    # only emit when a request phrase AND a recognizable service category co-occur,
    # so ordinary "looking for feedback / a new role" posts don't false-positive.
    m = _SOLICITATION_RE.search(lower)
    if m:
        category = _find_service(lower)
        if category:
            dept = SERVICE_DEPARTMENT.get(category)
            extra = {"service": category, **_extract_solicitation_meta(text)}
            out.append(_signal(SignalType.SOLICITATION, apex, url, _snippet(text, m),
                               intent_axis=category, department=dept, extra=extra))
    return out


def classify_document(doc: ParsedDocument, apex: str) -> list[CandidateRecord]:
    links_text = " ".join(f"{link.href} {link.text}" for link in doc.links)
    return detect_signals(doc.text, doc.url, apex, links_text=links_text)


def _infer_department(text: str) -> str | None:
    for keyword, dept in DEPARTMENT_BY_ROLE.items():
        if keyword in text:
            return dept
    return None


def _find_tech(text: str) -> str | None:
    for tech in KNOWN_TECH:
        if tech in text:
            return tech
    return None


def _find_all_tech(text: str) -> list[str]:
    return [tech for tech in sorted(KNOWN_TECH) if re.search(rf"\b{re.escape(tech)}\b", text)]


def _find_service(text: str) -> str | None:
    """The service category a solicitation is for (what they want to buy)."""
    for category, phrases in SERVICE_AXES.items():
        if any(phrase in text for phrase in phrases):
            return category
    return None


# Budget: "$2000", "$2,000 USD", "budget: 2000 usd", "€1.5k".
_BUDGET_RE = re.compile(
    r"(?:budget[:\s]*)?([$€£]\s?\d[\d,]*(?:\.\d+)?\s?k?|\b\d[\d,]*\s?(?:usd|eur|gbp))",
    re.IGNORECASE,
)
# Timeline: "30 days", "1 month", "2-3 weeks", "Timeline: 30 days".
_TIMELINE_RE = re.compile(r"\b(\d+(?:\s*[-–]\s*\d+)?)\s*(day|days|week|weeks|month|months)\b",
                          re.IGNORECASE)
_ENGAGEMENT_TERMS = ("freelancer", "freelance", "agency", "contractor", "contract",
                     "consultant", "full-time", "part-time")


def _extract_solicitation_meta(text: str) -> dict:
    """Lift the qualifying details a service request states (budget, timeline,
    engagement type, remote, tech stack) — what makes the lead actionable."""
    meta: dict = {}
    mb = _BUDGET_RE.search(text)
    if mb:
        meta["budget"] = mb.group(1).strip().rstrip(",.")
    mt = _TIMELINE_RE.search(text)
    if mt:
        meta["timeline"] = f"{mt.group(1)} {mt.group(2)}".strip()
    low = text.lower()
    engagement = [t for t in _ENGAGEMENT_TERMS if t in low]
    if engagement:
        # normalize freelance/freelancer -> one token
        meta["engagement"] = sorted({"freelance" if e.startswith("freelance") else e
                                     for e in engagement})
    if "remote" in low:
        meta["remote"] = True
    stack = [t for t in SOLICITATION_STACK if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low)]
    if stack:
        meta["stack"] = stack
    return meta
