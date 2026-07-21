"""reddit_search collector (spec 03 §7) — people posting requirements, across Reddit.

This is the "someone said what they need" firehose. Instead of watching a fixed set
of subreddits, it uses Reddit's public search to find posts that state a requirement —
"looking for a web developer", "can anyone recommend a designer", "in the market for
a CRM" — anywhere on Reddit, and keeps only the ones the classifier confirms are an
actual service request (solicitation).

Each kept post becomes a lead: anchored on the company it names (a link in the post)
when there is one, otherwise on the poster (u/handle) so an individual's request is
still captured — with the requirement (service / budget / timeline / stack) extracted
and the post permalink as the thing to reply to.

Public data via Reddit's search API; honors its terms and rate limits (production
wants a free Reddit app — auth_kind=oauth).
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
from ..textutil import company_slug, first_external_domain
from .remoteok import NON_COMPANY_HOSTS

# Never anchor a lead to Reddit's own hosts (a self-post links to reddit.com).
_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {"reddit.com", "redd.it", "redditmedia.com", "i.redd.it"}
_SKIP_AUTHORS = {"", "[deleted]", "automoderator"}

# Requirement phrasing to search for across Reddit (URL-encoded, newest first).
_QUERIES = (
    '"looking for a web developer"', '"looking for a web designer"',
    '"looking for a developer"', '"looking for a designer"',
    '"looking for a freelancer"', '"can anyone recommend a"',
    '"in the market for"', '"need a freelancer"', '"looking to hire a"',
)


def _search_urls() -> list[str]:
    from urllib.parse import quote
    return [f"https://www.reddit.com/search.json?q={quote(q)}&sort=new&limit=100&t=month"
            for q in _QUERIES]


@register
class RedditSearchCollector(BaseCollector):
    source_slug = "reddit_search"
    collector_slug = "reddit_search"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, auth_kind="oauth",
                                politeness_class="standard")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or _search_urls()

    def plan(self, ctx: CollectorContext) -> Iterable[FetchTask]:
        for url in self._seeds:
            yield FetchTask(url=url, seed_key=url)

    def parse(self, raw: RawResponse, ctx: CollectorContext) -> ParsedDocument:
        try:
            data = json.loads(raw.body)
        except (json.JSONDecodeError, ValueError):
            data = {}
        root = data.get("data", {}) or {} if isinstance(data, dict) else {}
        children = root.get("children", [])
        posts = [c.get("data", {}) for c in children if isinstance(c, dict)]
        return ParsedDocument(url=raw.url, structured={"posts": posts})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for post in doc.structured.get("posts", []):
            title = post.get("title", "")
            body = post.get("selftext", "")
            text = f"{title}. {body}"
            permalink = "https://www.reddit.com" + post.get("permalink", "")
            # Anchor on a company the post links to, else on the poster's handle.
            ext = post.get("url_overridden_by_dest") or post.get("url") or ""
            apex = first_external_domain(ext, exclude=_EXCLUDE_HOSTS)
            if apex:
                anchor, kind, name = apex, "domain", apex
            else:
                author = (post.get("author") or "").strip()
                if author.lower() in _SKIP_AUTHORS:
                    continue
                anchor, kind, name = company_slug(author), "name", f"u/{author}"
                if not anchor:
                    continue
            # Keep only posts the classifier confirms are an actual service request.
            signals = detect_signals(text, permalink, anchor)
            if not any(s.signal_type == "solicitation" for s in signals):
                continue
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": name, "display_name": name, "primary_domain": anchor,
                            "canonical_key": anchor, "anchor_kind": kind},
                evidence=EvidenceDraft(url=permalink, claim_type="company.domain",
                                       snippet=title[:200], confidence=0.55),
                blocking_hints={"apex_domain": anchor}))
            out.extend(signals)
        return out
