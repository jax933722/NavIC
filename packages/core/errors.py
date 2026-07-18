"""Typed error hierarchy.

The API layer maps these to the error envelope in docs/specs/06-backend-api.md §2.5.
"""

from __future__ import annotations


class NavicError(Exception):
    """Base for all platform errors."""

    code: str = "internal"


class InvalidRequest(NavicError):
    code = "invalid_request"


class NotFound(NavicError):
    code = "not_found"


class Conflict(NavicError):
    code = "conflict"


class Unprocessable(NavicError):
    code = "unprocessable"


class RateLimited(NavicError):
    code = "rate_limited"


class EvidenceRequired(Unprocessable):
    """Raised when a claim would be created without provenance (invariant I2)."""

    code = "evidence_required"
