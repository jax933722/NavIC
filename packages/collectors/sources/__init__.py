"""Source collectors. Importing this package registers the built-in collectors."""

from . import (  # noqa: F401  (self-register via @register)
    company_web,
    funding,
    github,
    greenhouse,
    hackernews,
    linkedin,
    news,
    producthunt,
    reddit,
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
]
