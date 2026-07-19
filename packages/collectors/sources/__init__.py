"""Source collectors. Importing this package registers the built-in collectors."""

from . import company_web, rss_blog  # noqa: F401  (self-register via @register)

__all__ = ["company_web", "rss_blog"]
