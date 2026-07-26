"""signals — detect and classify buying signals from documents (spec 05 §2).

Deterministic pattern classifiers (the cheap first tier; an LLM path is added in
M2's extraction upgrade). Each detected signal becomes an evidence-backed
CandidateRecord the pipeline attaches to a company.
"""

from .classifiers import classify_document, detect_signals
from .taxonomy import DEPARTMENT_BY_ROLE, SIGNAL_DEFAULT_STRENGTH, SignalType

__all__ = [
    "classify_document",
    "detect_signals",
    "SignalType",
    "SIGNAL_DEFAULT_STRENGTH",
    "DEPARTMENT_BY_ROLE",
]
