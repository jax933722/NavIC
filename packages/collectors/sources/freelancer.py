"""freelancer collector (spec 03 §7) — Freelancer.com marketplace projects.

Freelancer.com publishes an official public API for active projects
(https://www.freelancer.com/api/projects/0.1/projects/active/) — buyers posting paid
work ("Need a Shopify developer, budget $2000"). This is a true buyer marketplace: the
poster is an in-market buyer, not a freelancer advertising. We keep the projects the
classifier confirms are a real service request and extract service/budget/timeline.

Anchoring: marketplace projects are posted under an anonymous owner id (no company
domain), so we anchor the lead on the project itself (freelancer/<id>, name-only) and
keep the project URL as the place to respond. Public API; honors its terms.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register
from ..textutil import company_slug


def _budget_text(project: dict) -> str:
    """Render the structured budget so the classifier can lift it into the signal."""
    budget = project.get("budget") or {}
    sign = (project.get("currency") or {}).get("sign") or "$"
    lo, hi = budget.get("minimum"), budget.get("maximum")
    if lo and hi:
        return f" Budget {sign}{lo}-{sign}{hi}."
    if lo:
        return f" Budget {sign}{lo}."
    return ""


@register
class FreelancerCollector(BaseCollector):
    source_slug = "freelancer"
    collector_slug = "freelancer"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or [
            "https://www.freelancer.com/api/projects/0.1/projects/active/"
            "?limit=50&job_details=true&full_description=true",
        ]

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        result = data.get("result", {}) if isinstance(data, dict) else {}
        projects = result.get("projects", []) if isinstance(result, dict) else []
        return ParsedDocument(url=raw.url, structured={"projects": projects})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for project in doc.structured.get("projects", []):
            title = project.get("title", "")
            desc = project.get("description", "")
            pid = project.get("id") or ""
            seo = project.get("seo_url") or ""
            text = f"{title}. {desc}.{_budget_text(project)}"
            permalink = (f"https://www.freelancer.com/projects/{seo}" if seo
                         else f"https://www.freelancer.com/projects/{pid}")
            anchor = company_slug(f"freelancer-{pid}")
            if not anchor:
                continue
            name = f"freelancer/{pid}"
            # Keep only projects the classifier confirms are an actual service request.
            signals = detect_signals(text, permalink, anchor)
            if not any(s.signal_type == "solicitation" for s in signals):
                continue
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": anchor,
                            "canonical_key": anchor, "anchor_kind": "name"},
                evidence=EvidenceDraft(url=permalink, claim_type="company.domain",
                                       snippet=title[:200], confidence=0.55),
                blocking_hints={"apex_domain": anchor}))
            out.extend(signals)
        return out
