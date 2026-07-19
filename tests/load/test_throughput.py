"""Load / throughput harness (spec 09 §3.9).

Runs the pipeline over a synthetic corpus and asserts a throughput floor, and
that search over the corpus stays fast. This is a scaled-down smoke of NFR-5/6 —
the real 10x load test uses a larger synthetic set and the OpenSearch projection.
"""

from __future__ import annotations

import time

from extraction import EvidenceDraft, build_candidate
from pipeline import M0Pipeline
from search import SearchService
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

N = 300


def _repos():
    return dict(
        entities=InMemoryEntityRepo(), evidence=InMemoryEvidenceRepo(),
        signals=InMemorySignalRepo(), opportunities=InMemoryOpportunityRepo(),
        blocking=InMemoryBlockingRepo(), observations=InMemoryObservationRepo(),
        reviews=InMemoryReviewRepo(), merges=InMemoryMergeRepo(),
        timeline=InMemoryTimelineRepo(), transitions=InMemoryTransitionRepo(),
        edges=InMemoryEdgeRepo(),
    )


def _docs_for(i: int):
    d = f"co{i}.com"
    return [
        build_candidate(kind="entity", entity_type="company",
            attributes={"name": f"Co{i}", "display_name": f"Co{i}", "primary_domain": d},
            evidence=EvidenceDraft(url=f"https://{d}/", claim_type="company.domain",
                                   confidence=0.9)),
        build_candidate(kind="signal", signal_type="funding_raised",
            attributes={"company_domain": d, "intent_axis": "growth", "strength": 0.7},
            evidence=EvidenceDraft(url=f"https://{d}/x", claim_type="signal.funding_raised",
                                   confidence=0.6), blocking_hints={"apex_domain": d}),
        build_candidate(kind="signal", signal_type="pain_mention",
            attributes={"company_domain": d, "intent_axis": "crm", "strength": 0.7},
            evidence=EvidenceDraft(url=f"https://{d}/y", claim_type="signal.pain_mention",
                                   snippet="evaluating a CRM", confidence=0.6),
            blocking_hints={"apex_domain": d}),
    ]


def test_pipeline_throughput_floor():
    repos = _repos()
    pipe = M0Pipeline(**repos)
    start = time.perf_counter()
    for i in range(N):
        pipe.ingest(_docs_for(i), content_hash=f"h{i}")
    elapsed = time.perf_counter() - start

    assert len(repos["entities"].all_of_type("company")) == N
    docs_per_sec = (N * 3) / elapsed
    # Conservative floor; real hardware/CI is far faster. Guards against O(n^2) regressions.
    assert docs_per_sec > 100, f"throughput too low: {docs_per_sec:.0f} candidates/s"


def test_search_latency_over_corpus():
    repos = _repos()
    pipe = M0Pipeline(**repos)
    for i in range(N):
        pipe.ingest(_docs_for(i), content_hash=f"h{i}")
    svc = SearchService(entities=repos["entities"], signals=repos["signals"],
                        opportunities=repos["opportunities"], edges=repos["edges"],
                        evidence=repos["evidence"])
    start = time.perf_counter()
    _, results = svc.search("companies looking for CRM", limit=N * 2)
    elapsed = time.perf_counter() - start
    assert len(results) == N  # every seeded company has a CRM pain signal
    assert elapsed < 1.0, f"search too slow over {N} companies: {elapsed:.3f}s"
