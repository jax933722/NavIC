"""normalization — deterministic canonical forms.

Feeds both entity-resolution blocking (spec 04 §4) and matching. Pure functions,
no I/O, property-tested for idempotency.
"""

from .company_name import normalize_company_name
from .domain import apex_domain, normalize_host
from .person_name import name_soundex, normalize_person_name, soundex

__all__ = [
    "normalize_company_name",
    "apex_domain",
    "normalize_host",
    "normalize_person_name",
    "soundex",
    "name_soundex",
]
