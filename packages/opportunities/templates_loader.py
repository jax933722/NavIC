"""Opportunity template loader (spec 05 §3).

Templates are declarative YAML motifs, so new opportunity types are added as
config, not code. Loaded once and cached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

_TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class Template:
    id: str
    thesis: str
    intent_axis: str
    requires_any_signals: tuple[str, ...]
    min_signals: int
    suggested_department: str
    suggested_decision_maker_role: tuple[str, ...]
    base_intent_weight: float = 0.6
    require_intent_axis: tuple[str, ...] = field(default_factory=tuple)


@lru_cache
def load_templates() -> tuple[Template, ...]:
    templates: list[Template] = []
    for path in sorted(_TEMPLATE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        templates.append(
            Template(
                id=data["id"],
                thesis=data["thesis"],
                intent_axis=data["intent_axis"],
                requires_any_signals=tuple(data.get("requires_any_signals", [])),
                min_signals=int(data.get("min_signals", 1)),
                suggested_department=data.get("suggested_department", ""),
                suggested_decision_maker_role=tuple(data.get("suggested_decision_maker_role", [])),
                base_intent_weight=float(data.get("base_intent_weight", 0.6)),
                require_intent_axis=tuple(data.get("require_intent_axis", [])),
            )
        )
    return tuple(templates)
