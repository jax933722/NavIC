"""Source collectors. Importing this package registers the built-in collectors."""

from . import (  # noqa: F401  (self-register via @register)
    company_web,
    funding,
    github,
    greenhouse,
    hackernews,
    hn_freelance,
    linkedin,
    news,
    producthunt,
    reddit,
    reddit_forhire,
    rss_blog,
)

__all__ = [
    "company_web",
    "rss_blog",
    "github",
    "hackernews",
    "reddit",
    "producthunt",
    "linkedin",
    "greenhouse",
    "news",
    "funding",
    "hn_freelance",
    "reddit_forhire",
]
