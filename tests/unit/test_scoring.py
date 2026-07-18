from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from opportunities import Tier
from scoring import (
    SignalInput,
    buying_intent,
    evidence_score,
    freshness,
    opportunity_score,
    tier_multiplier,
)

NOW = datetime(2026, 7, 18, tzinfo=UTC)


def _sig(days_ago: float, strength=0.7, intent=1.0, stype="pain_mention"):
    return SignalInput(
        signal_type=stype,
        strength=strength,
        intent_weight=intent,
        detected_at=NOW - timedelta(days=days_ago),
    )


class TestBuyingIntent:
    def test_empty_is_zero(self):
        assert buying_intent([], NOW) == 0.0

    def test_more_independent_signals_compound(self):
        one = buying_intent([_sig(1)], NOW)
        two = buying_intent([_sig(1), _sig(1, stype="hiring")], NOW)
        assert two > one  # noisy-OR compounds

    def test_stale_signal_contributes_less(self):
        fresh = buying_intent([_sig(1)], NOW)
        stale = buying_intent([_sig(120)], NOW)
        assert fresh > stale

    def test_bounded(self):
        v = buying_intent([_sig(0, strength=1.0) for _ in range(20)], NOW)
        assert 0.0 <= v <= 1.0


class TestFreshness:
    def test_decays_monotonically(self):
        assert freshness([_sig(1)], NOW) > freshness([_sig(30)], NOW) > freshness([_sig(180)], NOW)

    def test_empty(self):
        assert freshness([], NOW) == 0.0


class TestEvidenceScore:
    def test_diversity_bonus(self):
        base = evidence_score([0.5, 0.5], distinct_source_domains=1)
        diverse = evidence_score([0.5, 0.5], distinct_source_domains=4)
        assert diverse > base

    def test_bounded(self):
        assert 0.0 <= evidence_score([5.0, 5.0], 10) <= 1.0


class TestOpportunityScore:
    def test_tier_multiplier_ordering(self):
        assert tier_multiplier(Tier.GOLD) > tier_multiplier(Tier.SILVER) > tier_multiplier(
            Tier.BRONZE
        )

    def test_gold_outranks_silver_all_else_equal(self):
        kw = dict(buying_intent_v=0.8, evidence_v=0.7, freshness_v=0.9)
        gold = opportunity_score(tier=Tier.GOLD, **kw)
        silver = opportunity_score(tier=Tier.SILVER, **kw)
        assert gold > silver

    def test_strong_bronze_can_beat_weak_silver(self):
        strong_bronze = opportunity_score(
            tier=Tier.BRONZE, buying_intent_v=1.0, evidence_v=1.0, freshness_v=1.0
        )
        weak_silver = opportunity_score(
            tier=Tier.SILVER, buying_intent_v=0.1, evidence_v=0.1, freshness_v=0.1
        )
        assert strong_bronze > weak_silver  # intent can override band (invariant O3)

    def test_monotonic_in_buying_intent(self):
        kw = dict(tier=Tier.SILVER, evidence_v=0.5, freshness_v=0.5)
        low = opportunity_score(buying_intent_v=0.2, **kw)
        high = opportunity_score(buying_intent_v=0.9, **kw)
        assert high > low

    @given(
        bi=st.floats(0, 1),
        es=st.floats(0, 1),
        fr=st.floats(0, 1),
    )
    def test_always_bounded(self, bi, es, fr):
        v = opportunity_score(tier=Tier.GOLD, buying_intent_v=bi, evidence_v=es, freshness_v=fr)
        assert 0.0 <= v <= 1.0
