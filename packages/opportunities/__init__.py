"""opportunities — assemble opportunities and classify Gold/Silver/Bronze.

Tiering is a deterministic gate over presence-of-fields (spec 05 §4, invariant O2).
"""

from .tiering import OpportunityPresence, Tier, classify

__all__ = ["Tier", "OpportunityPresence", "classify"]
