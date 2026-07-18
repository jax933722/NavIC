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
    InMemoryBlockingRepo,
    InMemoryEdgeRepo,
    InMemoryEntityRepo,
    InMemoryEvidenceRepo,
    InMemoryMergeRepo,
    InMemoryObservationRepo,
    InMemoryOpportunityRepo,
    InMemoryReviewRepo,
    InMemorySignalRepo,
    InMemoryTimelineRepo,
    InMemoryTransitionRepo,
)


@dataclass
class AppState:
    entities: InMemoryEntityRepo
    evidence: InMemoryEvidenceRepo
    signals: InMemorySignalRepo
    opportunities: InMemoryOpportunityRepo
    blocking: InMemoryBlockingRepo
    observations: InMemoryObservationRepo
    reviews: InMemoryReviewRepo
    merges: InMemoryMergeRepo
    timeline: InMemoryTimelineRepo
    transitions: InMemoryTransitionRepo
    edges: InMemoryEdgeRepo

    @property
    def pipeline(self) -> M0Pipeline:
        # Shared repos so resolution/timeline/transitions accumulate across requests.
        return M0Pipeline(
            entities=self.entities,
            evidence=self.evidence,
            signals=self.signals,
            opportunities=self.opportunities,
            blocking=self.blocking,
            observations=self.observations,
            reviews=self.reviews,
            merges=self.merges,
            timeline=self.timeline,
            transitions=self.transitions,
            edges=self.edges,
        )


def new_state() -> AppState:
    return AppState(
        entities=InMemoryEntityRepo(),
        evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(),
        opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(),
        observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(),
        merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(),
        transitions=InMemoryTransitionRepo(),
        edges=InMemoryEdgeRepo(),
    )
