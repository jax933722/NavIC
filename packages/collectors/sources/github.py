"""github collector (spec 03 §7) — API-first, JSON not HTML.

From a company's GitHub org payload it emits the company (via its website),
technology-adoption signals (languages), and org members as people with company
context. Another structurally different source added with only a module + @register.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from normalization import apex_domain
from parsing import ParsedDocument

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register


@register
class GithubOrgCollector(BaseCollector):
    source_slug = "github"
    collector_slug = "github_org"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, auth_kind="api_key",
                                politeness_class="aggressive-with-api")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or []

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            org = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            org = {}
        return ParsedDocument(url=raw.url, structured={"org": org})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        org = doc.structured.get("org", {})
        website = org.get("blog") or org.get("website") or org.get("html_url", "")
        apex = apex_domain(website)
        if not apex:
            return []
        name = org.get("name") or org.get("login") or apex
        out: list[CandidateRecord] = [
            build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": apex,
                            "canonical_key": apex, "github_org": org.get("login")},
                evidence=EvidenceDraft(url=doc.url, claim_type="company.domain",
                                       snippet=f"GitHub org {org.get('login')}", confidence=0.8),
                blocking_hints={"apex_domain": apex, "github_org": org.get("login")},
            )
        ]
        for lang in org.get("languages", []):
            out.append(build_candidate(
                kind="signal", signal_type="tech_adoption",
                attributes={"company_domain": apex, "intent_axis": lang.lower(),
                            "tech": lang.lower(), "strength": 0.5},
                evidence=EvidenceDraft(url=doc.url, claim_type="signal.tech_adoption",
                                       snippet=f"Uses {lang}", confidence=0.6),
                blocking_hints={"apex_domain": apex}))
        for member in org.get("members", []):
            fullname = member.get("name") or member.get("login")
            out.append(build_candidate(
                kind="entity", entity_type="person",
                attributes={"full_name": fullname, "name": fullname,
                            "current_role": member.get("role", "Engineer"),
                            "github_handle": member.get("login"),
                            "company_apex": apex, "company_domain": apex},
                evidence=EvidenceDraft(url=doc.url, claim_type="person.role",
                                       snippet=f"{fullname} @ {org.get('login')}", confidence=0.65),
                blocking_hints={"github_handle": member.get("login"), "company_apex": apex}))
        return out
