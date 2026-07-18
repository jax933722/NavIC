"""Graph builder — writes typed, evidence-backed edges idempotently (spec 02 §4)."""

from __future__ import annotations

# Roles considered decision-makers / leadership (drives Gold qualification).
LEADERSHIP_ROLE_TOKENS = (
    "ceo", "cto", "coo", "cfo", "cmo", "cro", "founder", "president",
    "vp", "vice president", "head", "director", "chief",
)


def is_leadership_role(role: str | None) -> bool:
    if not role:
        return False
    low = role.lower()
    return any(tok in low for tok in LEADERSHIP_ROLE_TOKENS)


class GraphBuilder:
    def __init__(self, edges):
        self._edges = edges

    def works_at(self, *, person_id: int, company_id: int, role: str | None,
                 evidence_ids: list[int], confidence: float = 0.7):
        """person --works_at--> company, carrying the role + relationship evidence."""
        return self._edges.upsert(
            src_entity_id=person_id, dst_entity_id=company_id, edge_type="works_at",
            attributes={"role": role, "leadership": is_leadership_role(role)},
            confidence=confidence, evidence_ids=evidence_ids,
        )
