"""In-process crawl executor (the durable Temporal variant needs a server)."""

from datetime import UTC, datetime, timedelta

from scheduler import CrawlTarget, InProcessExecutor

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


def _t(seed, hours_ago, cadence_h=24, value=0.0):
    return CrawlTarget(seed_key=seed, collector_slug="company_web",
                       base_cadence=timedelta(hours=cadence_h), value_score=value,
                       last_crawled=NOW - timedelta(hours=hours_ago))


def test_runs_only_due_targets_and_marks_crawled():
    ran = []
    ex = InProcessExecutor()
    targets = [_t("stale.com", 48), _t("fresh.com", 1)]
    res = ex.run_due(targets, runner=lambda t: (ran.append(t.seed_key) or 3), now=NOW)
    assert res.ran == 1 and "stale.com" in ran and "fresh.com" not in ran
    assert res.candidates == 3
    # Marked crawled -> not due again this tick.
    stale = next(t for t in targets if t.seed_key == "stale.com")
    assert not stale.is_due(NOW)


def test_isolates_a_failing_target():
    def runner(t):
        if t.seed_key == "bad.com":
            raise RuntimeError("boom")
        return 2

    ex = InProcessExecutor()
    res = ex.run_due([_t("bad.com", 48), _t("good.com", 48)], runner=runner, now=NOW)
    assert res.errors == 1 and res.ran == 1 and res.candidates == 2


def test_value_score_updates_from_output():
    ex = InProcessExecutor()
    t = _t("x.com", 48)
    ex.run_due([t], runner=lambda _t: 10, now=NOW)  # 10 candidates -> value ~1.0
    assert t.value_score == 1.0
