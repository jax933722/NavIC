"""Source collectors. Importing this package registers the built-in collectors."""

from . import company_web  # noqa: F401  (registers company_web via @register)

__all__ = ["company_web"]
