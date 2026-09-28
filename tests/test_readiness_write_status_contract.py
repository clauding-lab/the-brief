"""R2 fix 10: the Brief judges EconDelta's typed `write_status` contract.

Same rules as the producer's `utils/schema.py::WriteStatus`: a present receipt
must be well formed all the way down its legs, and a failed leg can never hide
under a healthier parent. Absence stays "unconfirmed" (legacy producers). The
approved-press override stage has its own receipt: a problem there is reported
(degraded), never charged to the daily write, and never read as success.
"""
import copy
import json

import pytest

from brief.econdelta import EconDeltaSnapshot
from brief.readiness import assess
from tests.test_readiness import NOW, OBS
from tests.upstream_liveness import POLLED_UPSTREAM

T = "2026-09-24T21:00:00Z"  # an attempt a few hours before NOW, in the producer's own "Z" spelling
# Serialised by EconDelta's WriteStatus model from real fix-8 receipt machinery
# (MonthlyReceipt/combine_monthly), attempt times pinned before NOW.
PRODUCER_SAMPLE = json.loads("""{
 "daily": {"status": "ok", "attempted_at": "%(t)s", "reason": "rows confirmed"},
 "monthly": {"status": "failed", "attempted_at": "%(t)s", "confirmed_rows": 2,
  "reason": "chart_appenders: macro: cpi: 2 row(s) written and confirmed by exact readback; remittance: read failed (source fetch failed): RuntimeError; yield: no new official period: no auction since 2026-09-01",
  "legs": {"chart_appenders": {"status": "failed", "attempted_at": "%(t)s", "confirmed_rows": 2, "reason": "macro: ...",
   "legs": {"macro": {"status": "failed", "attempted_at": "%(t)s", "confirmed_rows": 2, "reason": "cpi: ...",
     "legs": {"cpi": {"status": "ok", "attempted_at": "%(t)s", "reason": "2 row(s) written and confirmed by exact readback",
                      "confirmed_rows": 2, "failures": [], "skips": []},
              "remittance": {"status": "failed", "attempted_at": "%(t)s", "reason": "read failed (source fetch failed): RuntimeError",
                             "confirmed_rows": 0, "skips": [],
                             "failures": [{"operation": "read", "category": "source fetch failed", "detail": "RuntimeError"}]}}},
    "yield": {"status": "skipped", "attempted_at": "%(t)s", "reason": "no new official period: no auction since 2026-09-01",
              "confirmed_rows": 0, "failures": [],
              "skips": [{"category": "no new official period", "detail": "no auction since 2026-09-01",
                         "newest_recorded": "2026-09-01", "lag_window_days": 45}]}}}}},
 "media_overrides": {"status": "skipped", "attempted_at": "%(t)s", "reason": "no active approved override needed writing",
                     "failures": []}
}""".replace("%(t)s", T))


def _assess(write_status):
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {"quote": 80}, {"quote": OBS}, write_status=write_status)
    return assess(snap, persisted_rows=[], now=NOW)


def _monthly_ok() -> dict:
    """The sample with its one failed leg repaired: every level honestly ok."""
    status = copy.deepcopy(PRODUCER_SAMPLE)
    remit = status["monthly"]["legs"]["chart_appenders"]["legs"]["macro"]["legs"]["remittance"]
    # Fix 4: publication lag names its newest recorded month and the producer's accepted lag
    # window for the series (remittance: sentinel "monthly", 45 days; inside it at NOW).
    remit.update(status="skipped", failures=[], skips=[{"category": "no new official period", "detail": "Aug",
                                                        "newest_recorded": "2026-08-01",
                                                        "lag_window_days": 45}])
    for node in (status["monthly"], status["monthly"]["legs"]["chart_appenders"],
                 status["monthly"]["legs"]["chart_appenders"]["legs"]["macro"]):
        node["status"] = "ok"
    return status


def test_the_producers_own_nested_failure_holds_as_a_failed_write_not_a_malformed_one():
    result = _assess(PRODUCER_SAMPLE)
    assert result.state == "hold"
    assert result.reasons[0].startswith("monthly persistence failed: chart_appenders: macro:")


def test_a_fully_confirmed_producer_receipt_is_ready():
    assert _assess(_monthly_ok()).state == "ready"


def _hidden_leg_failure() -> dict:
    status = copy.deepcopy(PRODUCER_SAMPLE)
    for node in (status["monthly"], status["monthly"]["legs"]["chart_appenders"],
                 status["monthly"]["legs"]["chart_appenders"]["legs"]["macro"]):
        node["status"] = "ok"  # the remittance leg below still says failed
    return status


def _edit_cpi(**changes) -> dict:
    status = _monthly_ok()
    status["monthly"]["legs"]["chart_appenders"]["legs"]["macro"]["legs"]["cpi"].update(changes)
    return status


def _edit_monthly(**changes) -> dict:
    status = _monthly_ok()
    status["monthly"].update(changes)
    return status


WRITE_FAILURE = {"operation": "write", "category": "database write failed", "detail": "gross_npl_ratio (SupabaseWriteError)"}


def _monthly_leaf(**changes) -> dict:
    """A legless monthly receipt, so only its own fields (no parent row sum) decide."""
    leaf = {"status": "ok", "attempted_at": T, "reason": "r", "confirmed_rows": 1, "failures": [], "skips": []}
    return {**_monthly_ok(), "monthly": {**leaf, **changes}}


MALFORMED_MONTHLY = {
    "failed leg hidden under ok parents": _hidden_leg_failure(),
    "leaf failure reported ok": _edit_cpi(failures=[{"operation": "write", "category": "x", "detail": "y"}]),
    "ok leaf with no confirmed rows": _edit_cpi(confirmed_rows=0),
    "negative confirmed rows": _edit_cpi(confirmed_rows=-2),
    "boolean confirmed rows": _edit_cpi(confirmed_rows=True),
    "text confirmed rows": _edit_cpi(confirmed_rows="2"),
    "failure entry not an object": _edit_cpi(status="failed", failures=["boom"]),
    "failure entry missing its category": _edit_cpi(status="failed", failures=[{"operation": "write", "detail": "y"}]),
    "skips not a list": _edit_cpi(skips="none"),
    "reason not text": _edit_cpi(reason=5),
    "naive leg attempt time": _edit_cpi(attempted_at="2026-09-24T21:00:00"),
    "legs not an object": _edit_monthly(legs=["cpi"]),
    "parent rows disagree with its legs": _edit_monthly(confirmed_rows=9),
    "boolean rows where no parent sum can catch it": _monthly_leaf(confirmed_rows=True),
    "rowless failure reported ok": _monthly_leaf(confirmed_rows=None, failures=[WRITE_FAILURE]),
}


@pytest.mark.parametrize("write_status", list(MALFORMED_MONTHLY.values()), ids=list(MALFORMED_MONTHLY))
def test_a_receipt_that_breaks_the_contract_below_its_top_level_holds(write_status):
    result = _assess(write_status)
    assert (result.state, result.reasons) == ("hold", ("monthly persistence receipt malformed",))


@pytest.mark.parametrize("monthly", [_monthly_leaf(), _monthly_leaf(confirmed_rows=None)],
                         ids=["one confirmed row", "no row count"])
def test_a_legless_monthly_receipt_that_keeps_the_contract_is_ready(monthly):
    assert _assess(monthly).state == "ready"  # so the malformed twins above hold only for the broken rule


def test_an_additive_receipt_field_or_stage_from_a_newer_producer_does_not_hold():
    status = _monthly_ok()
    status["daily"] = {**status["daily"], "rows_sent": 41}
    status["weekly"] = {"anything": True}
    assert _assess(status).state == "ready"


# --- the approved-press override stage ------------------------------------------


def _with_overrides(receipt) -> dict:
    return {**_monthly_ok(), "media_overrides": receipt}


def test_an_unconfirmed_override_write_degrades_but_never_holds_or_reads_as_ready():
    result = _assess(_with_overrides({
        "status": "failed", "attempted_at": T,
        "reason": "readback failed (write unconfirmed): gross_npl_ratio sent; override rows have no exact readback",
        "failures": [{"operation": "readback", "category": "write unconfirmed",
                      "detail": "gross_npl_ratio sent; override rows have no exact readback"}]}))
    assert result.state == "degraded"
    assert result.reasons == (("approved press override persistence failed: readback failed (write unconfirmed): "
                               "gross_npl_ratio sent; override rows have no exact readback"),)


# R2 fix H2: EconDelta now reads an approved override's press rows back by exact
# (metric_id, as_of) key. This is the receipt it emits when both ids written for the
# production override (NPL 32.78 @ 2026-06-30 via The Daily Star: gross_npl_ratio and its
# banking_npl_pct alias) read back exactly -- the same literal as EconDelta
# tests/test_media_override_readback.py::CONFIRMED_NPL_RECEIPT, plus an attempt time.
CONFIRMED_OVERRIDE = {"status": "ok", "attempted_at": T, "confirmed_rows": 2, "failures": [],
                      "reason": "2 row(s) written and confirmed by exact readback"}


def test_an_active_override_confirmed_by_exact_readback_reads_ready():
    result = _assess(_with_overrides(CONFIRMED_OVERRIDE))
    assert (result.state, result.reasons) == ("ready", ())


# EconDelta's receipts when the readback disproves, misses or cannot read a sent press row.
READBACK_FAILURES = {
    "different value": ("readback mismatch", "banking_npl_pct 2026-06-30", 1),
    "row missing": ("readback missing", "banking_npl_pct 2026-06-30", 1),
    "reader error": ("readback unavailable", "banking_npl_pct, gross_npl_ratio (SupabaseReadError)", 0),
}


@pytest.mark.parametrize("category,detail,rows", list(READBACK_FAILURES.values()), ids=list(READBACK_FAILURES))
def test_an_override_readback_failure_degrades_but_never_holds_or_reads_as_ready(category, detail, rows):
    reason = f"readback failed ({category}): {detail}" + (
        f"; {rows} row(s) written and confirmed by exact readback" if rows else "")
    result = _assess(_with_overrides({
        "status": "failed", "attempted_at": T, "reason": reason, "confirmed_rows": rows,
        "failures": [{"operation": "readback", "category": category, "detail": detail}]}))
    assert (result.state, result.reasons) == ("degraded", (f"approved press override persistence failed: {reason}",))


OVERRIDE_FAILED = {"status": "failed", "attempted_at": T, "reason": "write failed", "failures": [WRITE_FAILURE]}


@pytest.mark.parametrize("receipt", [None, "ok", {"status": "done", "attempted_at": T},
                                     {"status": "failed", "attempted_at": "2026-09-24T21:00:00"},
                                     {**OVERRIDE_FAILED, "status": "ok"}, {**OVERRIDE_FAILED, "status": "skipped"}],
                         ids=["null", "string", "unknown status", "naive time",
                              "rowless failure reported ok", "rowless failure reported skipped"])
def test_a_malformed_override_receipt_holds(receipt):
    result = _assess(_with_overrides(receipt))
    assert (result.state, result.reasons) == ("hold", ("media_overrides persistence receipt malformed",))


def test_no_override_to_write_and_a_pre_fix_producer_without_the_stage_both_stay_ready():
    assert _assess(_monthly_ok()).state == "ready"  # skipped stage present
    legacy = {k: v for k, v in _monthly_ok().items() if k != "media_overrides"}
    assert _assess(legacy).state == "ready"
