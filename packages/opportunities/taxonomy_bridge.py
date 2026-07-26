"""Decision-maker inference (spec 05 §5.1).

Maps a department to a suggested decision-maker role for Silver opportunities,
preferring the department's canonical map and falling back to the template's list.
"""

from __future__ import annotations

from signals.taxonomy import DECISION_MAKER_BY_DEPARTMENT


def decision_maker_for(department: str, template_roles: tuple[str, ...]) -> str | None:
    if department and department in DECISION_MAKER_BY_DEPARTMENT:
        return DECISION_MAKER_BY_DEPARTMENT[department][0]
    if template_roles:
        return template_roles[0]
    return None
