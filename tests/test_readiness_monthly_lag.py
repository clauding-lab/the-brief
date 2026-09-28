"""R2 fix 4: a monthly leg that wrote nothing is judged by WHY, leg by leg.

Healthy (informational, never degrading):
- a SOURCE leg that read BB's own listing and found no month after the newest one already
  recorded ("no new official period"), while that newest month is still inside the accepted
  lag window EconDelta states with it (fix 4 round 1: its sentinel vintage policy, ruling E1 --
  remittance "monthly" 45 days, imports "quarterly" 165 days for BB's ~2-month MEI lag),
  counted from the month's end (brief.cadence.month_end);
- a DERIVED leg (CPI, M2) whose own daily table holds nothing newer ("no newer database
  vintage") ONLY when EconDelta's upstream source poll for that family is ok (fix 5). A
  database reread alone cannot tell BB's lag from a scraper dead for months.

Everything else a leg reports -- a guard refusal, a source that went backwards, a lag past
the window or with no dated month, an unknown or unitemised reason -- degrades, naming the
leg, even when a sibling leg confirmed rows. Degraded is log-only: it never holds and never
alerts (brief/cli.py). Legacy receipts without legs keep today's single stage reason.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from brief.econdelta import EconDeltaSnapshot
from brief.readiness import assess
from tests.test_readiness import NOW
from tests.upstream_liveness import CONTRACT, POLLED_UPSTREAM, STOPPED_UPSTREAM

T = "2026-09-24T21:00:00Z"  # the monthly attempt, a few hours before NOW (25 Sep 09:00 BDT)
NEW_PERIOD, DB_VINTAGE = "no new official period", "no newer database vintage"
WITHHELD, OLDER = "withheld by validation", "source older than recorded months"
DAILY_OK = {"status": "ok", "attempted_at": T, "reason": "rows confirmed"}


def skip(category: str, detail: str = "as reported", **extra) -> dict:
    return {"category": category, "detail": detail, **extra}


# The accepted lag window EconDelta attaches to each lag (sentinel/cadence.py
# GRACE_DAYS_BY_CADENCE: remittance_usd_mn_monthly "monthly", imports_usd_mn_monthly "quarterly").
REMIT_WINDOW, IMPORTS_WINDOW = 45, 165


def lag(newest_recorded: str | None = "2026-08-01", window: object = REMIT_WINDOW) -> dict:
    """BB's own listing has nothing after the newest recorded month (EconDelta _note_source_leg)."""
    return skip(NEW_PERIOD, "BB lists no month after those recorded (2026-09-01 not listed)",
                **({} if newest_recorded is None else {"newest_recorded": newest_recorded}),
                **({} if window is None else {"lag_window_days": window}))


def leaf(*skips: dict, rows: int = 0) -> dict:
    return {"status": "ok" if rows else "skipped", "attempted_at": T, "confirmed_rows": rows,
            "reason": "as reported", "failures": [], "skips": list(skips)}


def parent(legs: dict) -> dict:
    """A parent's status and rows follow its legs, exactly as EconDelta's combine_monthly does."""
    states = {leg["status"] for leg in legs.values()}
    return {"status": "failed" if "failed" in states else "ok" if "ok" in states else "skipped",
            "attempted_at": T, "reason": "as reported", "legs": legs,
            "confirmed_rows": sum(leg.get("confirmed_rows") or 0 for leg in legs.values())}


def caught_up(**overrides: dict) -> dict:
    """The producer's real nesting: monthly -> chart_appenders -> macro -> its four legs.

    Months as the real producer has them on 25 Sep: remittance through August (BB's page
    lists a month early the next month); imports through June at best (BB's MEI PDF runs ~2
    months behind -- EconDelta sentinel/cadence.py: the issue live on 22 Aug carried May).
    """
    macro = {"cpi": leaf(skip(DB_VINTAGE)), "remittance": leaf(lag("2026-08-01", REMIT_WINDOW)),
             "imports": leaf(lag("2026-06-01", IMPORTS_WINDOW)), "m2": leaf(skip(DB_VINTAGE)),
             **overrides}
    return {"daily": DAILY_OK, "monthly": parent({"chart_appenders": parent({"macro": parent(macro)})})}


def judge(write_status: dict, *, sources: dict | None = None, now: datetime = NOW):
    """Captured an hour before `now` on the same Bangladesh day, attempted just before it."""
    stamped = json.loads(json.dumps(write_status).replace(T, (now - timedelta(hours=2)).isoformat()))
    snap = EconDeltaSnapshot(now - timedelta(hours=1), POLLED_UPSTREAM if sources is None else sources,
                             {}, {}, write_status=stamped)
    return assess(snap, persisted_rows=[], now=now)


def leg_reasons(result) -> list[str]:
    return [r for r in result.reasons if r.startswith("monthly ")]


# ── Healthy official lag ────────────────────────────────────────────────────────────────
BDT = timezone(timedelta(hours=6))


def past_window(leg: str, month: str, window: int) -> str:
    return (f"monthly {leg} leg: no new official period, but its newest recorded month {month} is past "
            f"its accepted {window}-day lag window (stale since BB published nothing newer)")


def test_bb_lag_inside_each_legs_accepted_window_with_live_cpi_m2_polls_is_ready_and_noted():
    result = judge(caught_up())
    assert (result.state, result.reasons) == ("ready", ())
    assert any("remittance" in note and "2026-08" in note and "45-day" in note for note in result.notes)
    assert any("imports" in note and "2026-06" in note and "165-day" in note for note in result.notes)


@pytest.mark.parametrize("now, newest", [
    (datetime(2026, 8, 22, 9, tzinfo=BDT), "2026-05-01"),  # EconDelta's recorded live fact: issue carried May
    (datetime(2026, 8, 23, 9, tzinfo=BDT), "2026-06-01"),  # best case: the next issue lands the next day
    (datetime(2026, 9, 28, 9, tzinfo=BDT), "2026-07-01"),  # fix-4 review date
], ids=["22-aug-may", "23-aug-june", "28-sep-july"])
def test_imports_normal_two_month_bb_lag_is_healthy_under_its_accepted_window(now, newest):
    """BB's MEI PDF runs ~2 months behind; EconDelta accepts that with a 165-day window, so the
    normal lag must be able to read healthy (the ruling names imports as a healthy-lag leg)."""
    result = judge(caught_up(imports=leaf(lag(newest, IMPORTS_WINDOW)),
                             remittance=leaf(rows=1)), now=now)
    assert (result.state, result.reasons) == ("ready", ())
    assert [n for n in result.notes if "imports" in n] == [
        (f"monthly imports leg: official publication lag (BB lists nothing after {newest[:7]}; "
         "inside its accepted 165-day lag window)")]


@pytest.mark.parametrize("leg, newest, window, now, healthy", [
    ("remittance", "2026-07-01", REMIT_WINDOW, datetime(2026, 9, 14, 12, tzinfo=timezone.utc), True),
    ("remittance", "2026-07-01", REMIT_WINDOW, datetime(2026, 9, 15, 12, tzinfo=timezone.utc), False),
    ("imports", "2026-03-01", IMPORTS_WINDOW, datetime(2026, 9, 12, 12, tzinfo=timezone.utc), True),
    ("imports", "2026-03-01", IMPORTS_WINDOW, datetime(2026, 9, 13, 12, tzinfo=timezone.utc), False),
    # 14 Sep 19:30 UTC is already 15 Sep 01:30 in Dhaka: day 46, past (the Brief's calendar is BDT)
    ("remittance", "2026-07-01", REMIT_WINDOW, datetime(2026, 9, 14, 19, 30, tzinfo=timezone.utc), False),
], ids=["remit-day-45-inside", "remit-day-46-past", "imports-day-165-inside", "imports-day-166-past",
        "remit-day-46-by-dhaka-date"])
def test_official_lag_is_healthy_only_inside_its_own_accepted_window(leg, newest, window, now, healthy):
    result = judge(caught_up(**{leg: leaf(lag(newest, window))}), now=now)
    assert (result.state == "ready") is healthy
    assert leg_reasons(result) == ([] if healthy else [past_window(leg, newest, window)])
    assert any(n.startswith(f"monthly {leg} leg: official publication lag") for n in result.notes) is healthy


@pytest.mark.parametrize("leg, newest, window", [
    ("remittance", "2026-03-01", REMIT_WINDOW), ("imports", "2026-02-01", IMPORTS_WINDOW)])
def test_a_bb_listing_stuck_for_months_is_not_healthy_lag(leg, newest, window):
    result = judge(caught_up(**{leg: leaf(lag(newest, window))}))
    assert result.state == "degraded" and result.snapshot_problem is None
    assert leg_reasons(result) == [past_window(leg, newest, window)]


@pytest.mark.parametrize("newest", [None, "Aug", 202608, "2026-10-01"],
                         ids=["not reported", "not a date", "not a string", "after today"])
def test_lag_without_a_verifiable_newest_month_is_not_healthy(newest):
    imports = (lag(None, IMPORTS_WINDOW) if newest is None
               else skip(NEW_PERIOD, newest_recorded=newest, lag_window_days=IMPORTS_WINDOW))
    result = judge(caught_up(imports=leaf(imports)))
    assert result.state == "degraded"
    assert [r for r in leg_reasons(result) if "imports" in r] == [
        ("monthly imports leg: no new official period, but no verifiable newest recorded month "
         "(lag window cannot be checked)")]


@pytest.mark.parametrize("window", [None, 0, -45, True, "45", 45.0],
                         ids=["not reported", "zero", "negative", "a bool", "a string", "a float"])
def test_lag_without_an_accepted_window_is_not_healthy(window):
    """August is inside remittance's real 45-day window on 25 Sep, but without a usable window
    stated by the producer the reader cannot check it, so it never reads healthy."""
    result = judge(caught_up(remittance=leaf(lag("2026-08-01", window))))
    assert result.state == "degraded"
    assert leg_reasons(result) == [
        ("monthly remittance leg: no new official period, but no accepted lag window reported "
         "(lag window cannot be checked)")]
    assert not any("remittance" in n for n in result.notes)


# ── Derived CPI/M2 legs: a database reread is not BB's lag ──────────────────────────────
def test_a_months_dead_cpi_m2_scraper_is_not_healthy_lag():
    """The daily table has nothing newer and the reread succeeded, but no upstream poll is live."""
    result = judge(caught_up(), sources=STOPPED_UPSTREAM)
    assert result.state == "degraded" and result.snapshot_problem is None
    assert [r for r in leg_reasons(result) if "CPI" in r or "M2" in r] == [
        ("monthly cpi leg: no newer database vintage, and CPI upstream source-poll liveness is missing "
         "(a database reread cannot show BB publication lag)"),
        ("monthly m2 leg: no newer database vintage, and M2 upstream source-poll liveness is missing "
         "(a database reread cannot show BB publication lag)")]


@pytest.mark.parametrize("cpi_poll, liveness", [
    ({**POLLED_UPSTREAM["cpi_upstream_poll"], "status": "stale"}, "stale"),  # scraper stopped polling
    (None, "not reported"),                                                  # entry absent
    ("ok", "unknown (malformed status entry)"),                              # entry not an object
    (["ok"], "unknown (malformed status entry)"),
    ({k: v for k, v in POLLED_UPSTREAM["cpi_upstream_poll"].items() if k != "status"}, "unknown"),
], ids=["stale", "absent", "malformed-text", "malformed-list", "object-without-status"])
def test_cpi_database_vintage_is_healthy_only_when_its_upstream_poll_is_ok(cpi_poll, liveness):
    """A months-dead CPI scraper: the database reread succeeds, but the upstream poll is stale,
    missing or unreadable. That must never read as BB publication lag."""
    sources = {k: v for k, v in POLLED_UPSTREAM.items() if k != "cpi_upstream_poll"}
    if cpi_poll is not None:
        sources["cpi_upstream_poll"] = cpi_poll
    result = judge(caught_up(), sources=sources)
    assert result.state == "degraded" and result.snapshot_problem is None
    assert leg_reasons(result) == [
        (f"monthly cpi leg: no newer database vintage, and CPI upstream source-poll liveness is {liveness} "
         "(a database reread cannot show BB publication lag)")]
    assert not any(n.startswith("monthly cpi leg") for n in result.notes)
    assert any(n.startswith("monthly m2 leg") for n in result.notes)  # the live family stays healthy


def test_only_the_family_whose_upstream_poll_stopped_is_named():
    sources = {**POLLED_UPSTREAM, "m2_upstream_poll": STOPPED_UPSTREAM["m2_upstream_poll"]}
    reasons = leg_reasons(judge(caught_up(), sources=sources))
    assert [r.split(":")[0] for r in reasons] == ["monthly m2 leg"]


@pytest.mark.parametrize("family", sorted(CONTRACT["families"]))
def test_each_contract_family_leg_is_bound_to_its_own_upstream_poll(family):
    """The shared contract names which monthly leg each liveness entry vouches for."""
    leg, label = CONTRACT["families"][family]["monthly_leg"], CONTRACT["families"][family]["label"]
    stopped = {**POLLED_UPSTREAM, family: STOPPED_UPSTREAM[family]}
    assert leg_reasons(judge(caught_up(**{leg: leaf(skip(DB_VINTAGE))}))) == []
    named = [r for r in leg_reasons(judge(caught_up(**{leg: leaf(skip(DB_VINTAGE))}), sources=stopped))]
    assert len(named) == 1 and named[0].startswith(f"monthly {leg} leg:") and f"{label} upstream" in named[0]


def test_database_vintage_on_a_leg_with_no_upstream_poll_is_not_healthy():
    status = caught_up()
    status["monthly"] = parent({"chart_appenders": status["monthly"]["legs"]["chart_appenders"],
                                "reserves": leaf(skip(DB_VINTAGE))})
    assert leg_reasons(judge(status)) == [
        ("monthly reserves leg: no newer database vintage, and no upstream source poll vouches for "
         "this leg (a database reread cannot show BB publication lag)")]


# ── Guard skips and unknown reasons degrade, even beside a confirmed sibling ───────────
@pytest.mark.parametrize("category", [WITHHELD, OLDER])
def test_a_guard_skip_degrades_even_when_a_sibling_leg_confirmed_rows(category):
    status = caught_up(cpi=leaf(rows=3), imports=leaf(skip(category, "July 18% off the stored value")))
    assert status["monthly"]["status"] == "ok"  # the stage itself reports success
    result = judge(status)
    assert (result.state, result.snapshot_problem) == ("degraded", None)  # never a hold, never an alert
    assert leg_reasons(result) == [f"monthly imports leg: {category}: July 18% off the stored value"]


@pytest.mark.parametrize("imports, reason", [
    (leaf(skip("not attempted", "database writes disabled")),
     "monthly imports leg: not attempted: database writes disabled"),
    (leaf(skip("a category this reader has never seen", "x")),
     "monthly imports leg: a category this reader has never seen: x"),
    (leaf(), "monthly imports leg skipped: reason not itemised"),
], ids=["not attempted", "unknown category", "no reason at all"])
def test_an_unknown_or_unitemised_leg_outcome_is_never_healthy(imports, reason):
    assert leg_reasons(judge(caught_up(imports=imports))) == [reason]


def test_a_withheld_value_inside_an_ok_leg_still_degrades():
    """CPI wrote one series but a guard refused another: the refusal is still reported."""
    result = judge(caught_up(cpi=leaf(skip(WITHHELD, "cpi_p2p_food_monthly outside [0, 30)"), rows=2)))
    assert leg_reasons(result) == [
        "monthly cpi leg: withheld by validation: cpi_p2p_food_monthly outside [0, 30)"]


@pytest.mark.parametrize("healthy_first", [True, False], ids=["healthy skip first", "refusal first"])
def test_every_skip_on_one_leg_is_judged_whatever_its_order(healthy_first):
    """A leg's healthy skip (CPI: no newer database vintage, upstream poll ok) never hides another
    skip on the same leg. Synthetic order: today's producer records guard skips before vintage
    skips, but the reader must not depend on that."""
    vintage, refused = skip(DB_VINTAGE), skip(WITHHELD, "cpi_p2p_food_monthly outside [0, 30)")
    cpi = leaf(*((vintage, refused) if healthy_first else (refused, vintage)))
    result = judge(caught_up(cpi=cpi))
    assert (result.state, result.snapshot_problem) == ("degraded", None)  # log-only, never a hold
    assert leg_reasons(result) == [
        "monthly cpi leg: withheld by validation: cpi_p2p_food_monthly outside [0, 30)"]
    assert [n for n in result.notes if n.startswith("monthly cpi leg")] == [
        "monthly cpi leg: no newer database vintage; CPI upstream source poll ok"]


def test_healthy_lag_never_softens_a_failed_sibling():
    failed = {"status": "failed", "attempted_at": T, "confirmed_rows": 0, "reason": "read failed",
              "skips": [], "failures": [{"operation": "read", "category": "source fetch failed", "detail": "E"}]}
    assert judge(caught_up(remittance=failed)).state == "hold"


# ── Legacy receipts keep today's behaviour ──────────────────────────────────────────────
def test_a_legless_skipped_monthly_receipt_keeps_its_single_stage_reason():
    result = judge({"daily": DAILY_OK, "monthly": {"status": "skipped", "attempted_at": T, "reason": "no new month"}})
    assert (result.state, result.reasons, result.notes) == ("degraded", ("monthly persistence skipped: no new month",), ())
