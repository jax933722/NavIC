"""ER F1 gate (spec 09 §3.3, §4).

Computes precision/recall/F1 for the company matcher against the labeled eval
set and FAILS the build if F1 drops below the baseline. A separate over-merge
canary assertion guards the highest risk (R1): near-duplicate distinct companies
must never cross the auto-merge threshold.
"""

from __future__ import annotations

from entities import score_company_pair
from entities.engine import AUTO_MERGE
from tests.data.er_company_pairs import PAIRS

F1_BASELINE = 0.85
DECISION_THRESHOLD = 0.5  # a pair is "predicted match" at p >= this


def _prf():
    tp = fp = fn = tn = 0
    for a, b, label in PAIRS:
        pred = score_company_pair(a, b) >= DECISION_THRESHOLD
        if pred and label:
            tp += 1
        elif pred and not label:
            fp += 1
        elif not pred and label:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def test_company_matcher_f1_meets_baseline():
    precision, recall, f1 = _prf()
    assert f1 >= F1_BASELINE, (
        f"F1 {f1:.3f} < baseline {F1_BASELINE} (P={precision:.3f} R={recall:.3f})"
    )


def test_over_merge_canaries_never_auto_merge():
    # Every labeled non-match must score below the AUTO_MERGE threshold.
    for a, b, label in PAIRS:
        if not label:
            p = score_company_pair(a, b)
            assert p < AUTO_MERGE, f"over-merge risk: {a['name']} ~ {b['name']} scored {p:.3f}"
