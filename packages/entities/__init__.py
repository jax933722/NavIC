"""entities — resolution engine (spec 04).

M0 ships a domain-exact resolver (hard rule from spec 04 §5.4). Blocking +
probabilistic matching + survivorship land in M1.
"""

from .blocking import company_blocking_keys, person_blocking_keys
from .engine import ResolutionEngine, ResolutionResult
from .matcher import score_company_pair, score_person_pair
from .resolution import DomainExactResolver
from .survivorship import Observation, project

__all__ = [
    "ResolutionEngine",
    "ResolutionResult",
    "DomainExactResolver",
    "company_blocking_keys",
    "person_blocking_keys",
    "score_company_pair",
    "score_person_pair",
    "Observation",
    "project",
]
