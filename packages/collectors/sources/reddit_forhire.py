"""reddit_forhire collector (spec 03 §7) — automated inbound from hiring subreddits.

Monitors the "someone wants to pay for work" subreddits — r/forhire, r/DesignJobs,
r/jobbit, r/hiring — where buyers post requests like "[Hiring] Need a Shopify
developer, $2k budget". Only the BUYER side is ingested: posts flaired/titled
"[Hiring]" (an employer looking to pay). The "[For Hire]" posts (freelancers
advertising themselves) are sellers and are skipped.

Each buyer post becomes the company it links to (domain parsed from the title/body,
full URL or bare) plus a solicitation signal, with service/budget/timeline/stack
lifted by the classifier. Public data via Reddit's Data API; honors its terms and
rate limits (production use needs a free Reddit app — auth_kind=oauth).
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
from ..textutil import first_external_domain

_SELF_HOSTS = {"reddit.com", "redd.it", "redditmedia.com", "imgur.com"}


def _is_buyer(post: dict) -> bool:
    """True for employer/buyer posts ("[Hiring]"), False for "[For Hire]" sellers."""
    flair = (post.get("link_flair_text") or "").strip().lower()
    title = (post.get("title") or "").lower()
    if "for hire" in flair or "[for hire]" in title:
        return False
    return flair == "hiring" or "[hiring]" in title


@register
class RedditForHireCollector(BaseCollector):
    source_slug = "reddit_forhire"
    collector_slug = "reddit_forhire"
    version = "0.1.0"
    # Production access to the Reddit Data API uses a (free) OAuth app; the public
    # listing JSON has the same shape for development.
    capabilities = Capabilities(supports_incremental=True, auth_kind="oauth",
                                politeness_class="standard")

    def __init__(self, seeds: list[str] | None = None):
        self._seeds = seeds or [
            "https://www.reddit.com/r/forhire/new.json?limit=100",
            "https://www.reddit.com/r/DesignJobs/new.json?limit=100",
        ]

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
            if not _is_buyer(post):
                continue  # skip "[For Hire]" (freelancers advertising, not buying)
            title = post.get("title", "")
            body = post.get("selftext", "")
            text = f"{title}. {body}"
            permalink = "https://www.reddit.com" + post.get("permalink", "")
            # Anchor on a company the post names (in the link or the text); skip if none.
            apex = first_external_domain(
                f"{post.get('url_overridden_by_dest') or ''} {text}", exclude=_SELF_HOSTS)
            if not apex:
                continue
            out.append(build_candidate(
                kind="entity", entity_type="company",
                attributes={"name": apex, "display_name": apex, "primary_domain": apex,
                            "canonical_key": apex},
                evidence=EvidenceDraft(url=permalink, claim_type="company.domain",
                                       snippet=title[:200], confidence=0.55),
                blocking_hints={"apex_domain": apex}))
            out.extend(detect_signals(text, permalink, apex))
        return out
