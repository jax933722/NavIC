"""Application state / composition root (spec 06, blueprint §7).

Holds the repository set the API reads from. In M0 these are in-memory repos so
the API is runnable without a database; wiring the SQLAlchemy repos over Postgres
is a one-line swap here (same protocols) once the DB stack is up. The API code
never changes — it depends only on the repository interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipeline import M0Pipeline
from storage.repositories import (
    InMemoryEntityRepo,
    InMemoryEvidenceRepo,
    InMemoryOpportunityRepo,
    InMemorySignalRepo,
)


@dataclass
class AppState:
    entities: InMemoryEntityRepo
    evidence: InMemoryEvidenceRepo
    signals: InMemorySignalRepo
    opportunities: InMemoryOpportunityRepo

    @property
    def pipeline(self) -> M0Pipeline:
        return M0Pipeline(
            entities=self.entities,
            evidence=self.evidence,
            signals=self.signals,
            opportunities=self.opportunities,
        )


def new_state() -> AppState:
    return AppState(
        entities=InMemoryEntityRepo(),
        evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(),
        opportunities=InMemoryOpportunityRepo(),
    )
