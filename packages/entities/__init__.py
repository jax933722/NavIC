"""entities — resolution engine (spec 04).

M0 ships a domain-exact resolver (hard rule from spec 04 §5.4). Blocking +
probabilistic matching + survivorship land in M1.
"""

from .resolution import DomainExactResolver, ResolutionResult

__all__ = ["DomainExactResolver", "ResolutionResult"]
