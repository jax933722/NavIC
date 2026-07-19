"""Source collectors. Importing this package registers the built-in collectors."""

from . import (  # noqa: F401  (self-register via @register)
    company_web,
    github,
    hackernews,
    rss_blog,
)

__all__ = ["company_web", "rss_blog", "github", "hackernews"]
