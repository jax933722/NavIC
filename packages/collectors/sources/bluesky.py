"""bluesky collector (spec 03 §7) — people posting requirements on Bluesky, no key.

Bluesky exposes a fully public, key-less search API (the AppView at
public.api.bsky.app) — no login, no app registration, no cost. This searches it for
buying-intent phrasing ("looking for a developer", "can anyone recommend a designer",
"in the market for") and keeps only the posts the classifier confirms are a real
service request (solicitation).

Each kept post becomes a lead: anchored on a company the post names (a link/domain in
the text) when there is one, else on the poster (bsky/handle) so an individual's
request is still captured — with the requirement (service/budget/timeline/stack)
extracted and the bsky.app permalink to reply to.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from urllib.parse import quote

from extraction import CandidateRecord, EvidenceDraft, build_candidate
from ingestion import RawResponse
from parsing import ParsedDocument
from signals import detect_signals

from ..base import BaseCollector, Capabilities, CollectorContext, FetchTask
from ..registry import register
from ..textutil import company_slug, first_external_domain
from .remoteok import NON_COMPANY_HOSTS

# Never anchor a lead to Bluesky's own hosts (a post links back to bsky.app).
_EXCLUDE_HOSTS = NON_COMPANY_HOSTS | {"bsky.app", "bsky.social", "atproto.com"}
_SKIP_HANDLES = {"", "handle.invalid"}

# Requirement phrasing to search Bluesky for (latest first).
_QUERIES = (
    "looking for a developer", "looking for a designer", "looking for a freelancer",
    "can anyone recommend a", "in the market for", "looking to hire a",
    "need a freelancer", "recommendations for a", "who can build me a",
)


def _search_urls() -> list[str]:
    return [f"https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
            f"?q={quote(q)}&sort=latest&limit=100" for q in _QUERIES]


def _permalink(uri: str, handle: str) -> str:
    """at://did/app.bsky.feed.post/<rkey> -> https://bsky.app/profile/<handle>/post/<rkey>."""
    rkey = uri.rsplit("/", 1)[-1] if uri else ""
    if handle and rkey:
        return f"https://bsky.app/profile/{handle}/post/{rkey}"
    return f"https://bsky.app/profile/{handle}" if handle else "https://bsky.app"


@register
class BlueskyCollector(BaseCollector):
    source_slug = "bluesky"
    collector_slug = "bluesky"
    version = "0.1.0"
    capabilities = Capabilities(supports_incremental=True, politeness_class="aggressive-with-api")

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
        posts = data.get("posts", []) if isinstance(data, dict) else []
        return ParsedDocument(url=raw.url, structured={"posts": posts})

    def normalize(self, doc: ParsedDocument, ctx: CollectorContext) -> list[CandidateRecord]:
        out: list[CandidateRecord] = []
        for post in doc.structured.get("posts", []):
            record = post.get("record", {}) if isinstance(post, dict) else {}
            text = (record.get("text") or "").strip()
            if not text:
                continue
            author = post.get("author", {}) if isinstance(post, dict) else {}
            handle = (author.get("handle") or "").strip()
            permalink = _permalink(post.get("uri", ""), handle)
            # Anchor on a company the post names, else on the poster's handle.
            apex = first_external_domain(text, exclude=_EXCLUDE_HOSTS)
            if apex:
                anchor, kind, name = apex, "domain", apex
            else:
                if handle.lower() in _SKIP_HANDLES:
                    continue
                short = handle.split(".")[0]
                anchor, kind, name = company_slug(short), "name", f"bsky/{handle}"
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
                                       snippet=text[:200], confidence=0.55),
                blocking_hints={"apex_domain": anchor}))
            out.extend(signals)
        return out
