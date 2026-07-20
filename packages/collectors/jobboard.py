"""Shared job-board logic (spec 03 §7).

Greenhouse, Lever, Ashby, and Workable all publish a company's open roles as public
JSON. The provider shapes differ, but what we do with them is identical: emit the
company, one hiring signal per open role (department from the role's own field or
inferred from its title), and — when a company is hiring across many roles at once —
an expansion/scaling signal. Each provider collector just normalizes its payload into
`{title, department, location, url}` jobs and calls `build_jobboard_candidates`.

Anchoring note: provider APIs return the ATS-hosted URL, not the company's marketing
domain, so the operator pairs each board with the company website in config (you know
the company — it's why you're watching its board). The normalized `company` dict
carries that website.
"""

from __future__ import annotations

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from normalization import apex_domain
from signals.taxonomy import DEPARTMENT_BY_ROLE


def department_for(title: str, explicit: str | None) -> str | None:
    """The role's stated department, else one inferred from its title."""
    if explicit:
        return explicit
    low = (title or "").lower()
    for keyword, dept in DEPARTMENT_BY_ROLE.items():
        if keyword in low:
            return dept
    return None


def build_jobboard_candidates(company: dict, jobs: list[dict]) -> list[CandidateRecord]:
    """company: {name, website, careers_url}. jobs: [{title, department, location, url}]."""
    website = company.get("website") or ""
    apex = apex_domain(website)
    if not apex:
        return []
    name = company.get("name") or apex
    page = company.get("careers_url") or website

    out: list[CandidateRecord] = [
        build_candidate(
            kind="entity", entity_type="company",
            attributes={"name": name, "display_name": name, "primary_domain": apex,
                        "canonical_key": apex},
            evidence=EvidenceDraft(url=page, claim_type="company.domain",
                                   snippet=f"Careers: {name}", confidence=0.75),
            blocking_hints={"apex_domain": apex}),
    ]
    for job in jobs:
        title = job.get("title", "")
        dept = department_for(title, job.get("department"))
        out.append(build_candidate(
            kind="signal", signal_type="hiring",
            attributes={"company_domain": apex, "intent_axis": "hiring",
                        "department": dept, "strength": 0.65, "weak": dept is None,
                        "role": title, "location": job.get("location")},
            evidence=EvidenceDraft(url=job.get("url") or page, claim_type="signal.hiring",
                                   snippet=f"Open role: {title}"[:200], confidence=0.75),
            blocking_hints={"apex_domain": apex}))
    if len(jobs) >= 5:
        out.append(build_candidate(
            kind="signal", signal_type="expansion",
            attributes={"company_domain": apex, "intent_axis": "scaling",
                        "strength": 0.6, "open_roles": len(jobs)},
            evidence=EvidenceDraft(url=page, claim_type="signal.expansion",
                                   snippet=f"{len(jobs)} open roles at {name}", confidence=0.65),
            blocking_hints={"apex_domain": apex}))
    return out
