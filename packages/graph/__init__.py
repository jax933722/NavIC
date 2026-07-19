"""graph — typed, evidence-backed relationship edges (spec 02).

M2/M4 build works_at (person->company) and can extend to uses_tech, hiring_for,
raised. Edges are plain rows (the source of truth); an AGE mirror is added later
as a derived query surface.
"""

from .builder import GraphBuilder
from .mirror import AgeGraphMirror, GraphMirror, NullMirror

__all__ = ["GraphBuilder", "GraphMirror", "NullMirror", "AgeGraphMirror"]
