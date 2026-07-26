"""extraction — turn parsed documents into candidate entities/signals + evidence.

This package owns the invariant: **no claim without evidence** (I2). The models
here make that impossible to violate — a candidate cannot be built without an
``EvidenceDraft``.
"""

from .evidence import CandidateRecord, EvidenceDraft, build_candidate
from .person import extract_people

__all__ = ["EvidenceDraft", "CandidateRecord", "build_candidate", "extract_people"]
