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
    SIGNAL_DEFAULT_STRENGTH,
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
