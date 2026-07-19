"""Repository provider (composition root for the API).

Endpoints work against a ``RepoBundle`` obtained from a provider, so the API is
datastore-agnostic: ``InMemoryProvider`` keeps the M0 behaviour (state in the
process), ``SqlProvider`` opens a Postgres session per unit of work. The endpoint
code is identical for both — the interface/adapter payoff (blueprint §7).

Backend is chosen by NAVIC_API_BACKEND ("memory" default, or "postgres").
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

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
class RepoBundle:
    entities: object
    evidence: object
    signals: object
    opportunities: object
    blocking: object
    observations: object
    reviews: object
    merges: object
    timeline: object
    transitions: object
    edges: object

    @property
    def pipeline(self) -> M0Pipeline:
        return M0Pipeline(
            entities=self.entities, evidence=self.evidence, signals=self.signals,
            opportunities=self.opportunities, blocking=self.blocking,
            observations=self.observations, reviews=self.reviews, merges=self.merges,
            timeline=self.timeline, transitions=self.transitions, edges=self.edges,
        )


class RepoProvider(Protocol):
    @contextmanager
    def bundle(self): ...  # -> Iterator[RepoBundle]


class InMemoryProvider:
    """Persistent in-memory repos shared across requests (single process)."""

    def __init__(self) -> None:
        self._bundle = RepoBundle(
            entities=InMemoryEntityRepo(), evidence=InMemoryEvidenceRepo(),
            signals=InMemorySignalRepo(), opportunities=InMemoryOpportunityRepo(),
            blocking=InMemoryBlockingRepo(), observations=InMemoryObservationRepo(),
            reviews=InMemoryReviewRepo(), merges=InMemoryMergeRepo(),
            timeline=InMemoryTimelineRepo(), transitions=InMemoryTransitionRepo(),
            edges=InMemoryEdgeRepo(),
        )

    @contextmanager
    def bundle(self):
        yield self._bundle


class SqlProvider:
    """A fresh Postgres session + SQL repos per unit of work; commits on success."""

    @contextmanager
    def bundle(self):
        from storage.db import session_scope
        from storage.sql_repositories import (
            SqlBlockingRepo,
            SqlEdgeRepo,
            SqlEntityRepo,
            SqlEvidenceRepo,
            SqlMergeRepo,
            SqlObservationRepo,
            SqlOpportunityRepo,
            SqlReviewRepo,
            SqlSignalRepo,
            SqlTimelineRepo,
            SqlTransitionRepo,
        )

        with session_scope() as s:
            yield RepoBundle(
                entities=SqlEntityRepo(s), evidence=SqlEvidenceRepo(s),
                signals=SqlSignalRepo(s), opportunities=SqlOpportunityRepo(s),
                blocking=SqlBlockingRepo(s), observations=SqlObservationRepo(s),
                reviews=SqlReviewRepo(s), merges=SqlMergeRepo(s),
                timeline=SqlTimelineRepo(s), transitions=SqlTransitionRepo(s),
                edges=SqlEdgeRepo(s),
            )


def get_provider() -> RepoProvider:
    backend = os.environ.get("NAVIC_API_BACKEND", "memory").lower()
    return SqlProvider() if backend == "postgres" else InMemoryProvider()
