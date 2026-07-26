from datetime import UTC, datetime, timedelta

from scheduler import CrawlTarget, Scheduler

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _t(seed, hours_ago, value=0.0, cadence_h=24):
    return CrawlTarget(
        seed_key=seed, collector_slug="company_web",
        base_cadence=timedelta(hours=cadence_h), value_score=value,
        last_crawled=NOW - timedelta(hours=hours_ago),
    )


def test_only_due_targets_are_planned():
    sched = Scheduler()
    fresh = _t("fresh.com", hours_ago=1, cadence_h=24)      # not due
    stale = _t("stale.com", hours_ago=48, cadence_h=24)     # due
    plan = sched.plan([fresh, stale], now=NOW)
    keys = [t.seed_key for t in plan]
    assert "stale.com" in keys and "fresh.com" not in keys


def test_never_crawled_is_maximally_overdue():
    sched = Scheduler()
    never = CrawlTarget("new.com", "company_web", base_cadence=timedelta(hours=24))
    plan = sched.plan([never], now=NOW)
    assert plan and plan[0].seed_key == "new.com"


def test_value_raises_priority_and_shortens_cadence():
    sched = Scheduler()
    hot = _t("hot.com", hours_ago=13, value=1.0, cadence_h=24)   # eff cadence 12h -> due
    cold = _t("cold.com", hours_ago=13, value=0.0, cadence_h=24)  # eff cadence 24h -> not due
    plan = sched.plan([hot, cold], now=NOW)
    assert [t.seed_key for t in plan] == ["hot.com"]


def test_priority_orders_by_value_times_staleness():
    sched = Scheduler()
    a = _t("a.com", hours_ago=48, value=0.9, cadence_h=24)
    b = _t("b.com", hours_ago=48, value=0.1, cadence_h=24)
    plan = sched.plan([a, b], now=NOW)
    assert plan[0].seed_key == "a.com"  # higher value wins at equal staleness


def test_mark_crawled_updates_state():
    sched = Scheduler()
    t = _t("x.com", hours_ago=48)
    sched.mark_crawled(t, now=NOW, value_score=0.8)
    assert t.last_crawled == NOW and t.value_score == 0.8
    assert not t.is_due(NOW)  # just crawled -> not due
