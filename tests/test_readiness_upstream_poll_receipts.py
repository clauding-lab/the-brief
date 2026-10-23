"""A live CPI/M2 upstream poll lets the Brief's healthy-lag gate pass (R2 fix H3).

EconDelta's daily fetch now writes one typed upstream-poll receipt per CPI/M2 page, and the
aggregate publishes them as `cpi_upstream_poll` / `m2_upstream_poll` (shared contract
`upstream_liveness_contract.live_upstream_polls`: status ok, with the family's last successful
poll time and age filled in). Under the fix-4 ruling a derived CPI/M2 leg's "no newer database
vintage" is healthy lag only when that family's poll is ok, so on a normal quiet night the
Brief can now say "ready". The entries are the producer's exact published shape (EconDelta
tests/test_upstream_poll_receipts.py pins the same contract entries), not a hand-written ok.
"""
from tests.test_readiness_monthly_lag import caught_up, judge, leg_reasons
from tests.upstream_liveness import LIVE_UPSTREAM, STOPPED_UPSTREAM


def test_live_upstream_polls_make_the_cpi_m2_database_vintage_healthy_lag_and_ready():
    result = judge(caught_up(), sources=LIVE_UPSTREAM)

    assert (result.state, result.reasons) == ("ready", ())
    assert "monthly cpi leg: no newer database vintage; CPI upstream source poll ok" in result.notes
    assert "monthly m2 leg: no newer database vintage; M2 upstream source poll ok" in result.notes


def test_the_live_entries_carry_the_polls_time_and_age_not_a_bare_ok():
    for key, entry in LIVE_UPSTREAM.items():
        assert entry["status"] == "ok" and entry["error"] is None, key
        assert entry["last_success"] and isinstance(entry["age_hours"], float), key


def test_the_same_quiet_night_without_live_polls_is_not_ready():
    result = judge(caught_up(), sources=STOPPED_UPSTREAM)

    assert result.state == "degraded"
    assert [r.split(",")[0] for r in leg_reasons(result)] == [
        "monthly cpi leg: no newer database vintage", "monthly m2 leg: no newer database vintage"]
