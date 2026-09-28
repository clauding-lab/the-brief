"""Readiness distinguishes dated data, upstream health and write receipts."""
from datetime import date, datetime, timezone

import pytest

from brief.econdelta import EconDeltaSnapshot
from brief.readiness import assess
from tests.upstream_liveness import POLLED_UPSTREAM

NOW = datetime(2026, 9, 25, 3, tzinfo=timezone.utc)
OBS = dict(metric_id="quote", value=80, unit="USD/barrel", as_of="2026-09-23",
           captured_at="2026-09-25T02:00:00+00:00", source="official",
           evidence="dated row", quality="verified", date_basis="observation")


def snapshot(**kwargs):
    return EconDeltaSnapshot(updated_at=NOW, sources_status=POLLED_UPSTREAM, data={"quote": 80},
        observations={"quote": OBS}, **kwargs)


def test_legacy_never_invents_write_success():
    result = assess(snapshot(), persisted_rows=[], now=NOW)
    assert result.state == "degraded"
    assert "unconfirmed" in " ".join(result.reasons)


def test_failed_write_holds_even_with_valid_observation():
    result = assess(snapshot(write_status={"daily": {"status": "failed", "attempted_at": NOW.isoformat()}}), persisted_rows=[], now=NOW)
    assert result.state == "hold"


def test_held_and_unknown_observations_do_not_become_current():
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {"quote": 80, "unknown": 12},
                            {"quote": {**OBS, "quality": "held"}})
    result = assess(snap, persisted_rows=[], now=NOW)
    assert result.state == "degraded"
    assert result.unavailable == ("unknown",)
    assert any("held" in reason for reason in result.reasons)


def test_identity_contradiction_holds():
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {"quote": 81}, {"quote": OBS})
    assert assess(snap, persisted_rows=[], now=NOW).state == "hold"


def test_source_poll_failure_not_disguised_by_successful_write():
    snap = EconDeltaSnapshot(NOW, {**POLLED_UPSTREAM, "cpi": {"status": "stale"}}, {"quote": 80},
        {"quote": OBS}, {"daily": {"status": "ok", "attempted_at": NOW.isoformat()},
                       "monthly": {"status": "skipped", "attempted_at": NOW.isoformat(), "reason": "no new month"}})
    assert assess(snap, persisted_rows=[], now=NOW).state == "degraded"


def test_legacy_consistent_dated_row_can_be_used_but_receipt_stays_unknown():
    from brief.schema import Metric
    row = Metric(id="quote", label="Quote", value=80, unit="USD/barrel", source="official",
                 as_of=date(2026, 9, 23), cadence="daily")
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {"quote": 80})
    result = assess(snap, persisted_rows=[row], now=NOW)
    assert result.state == "degraded" and not result.unavailable


def test_builder_date_or_value_disagreement_holds():
    from brief.schema import Metric
    row = Metric(id="quote", label="Quote", value=82, unit="USD/barrel", source="official",
                 as_of=date(2026, 9, 23), cadence="daily")
    assert assess(snapshot(), persisted_rows=[row], now=NOW).state == "hold"


# ── Policy-corridor writer confirmations (EconDelta WRITER_CONFIRMATION_IDS) ──
RECEIPTS = {stage: {"status": "ok", "attempted_at": NOW.isoformat()} for stage in ("daily", "monthly")}
CORRIDOR = {"policy_rate_repo": 9.5, "policy_rate_sdf": 7.5, "policy_rate_slf": 11.0}


def confirmation(mid, value):
    return {"metric_id": mid, "value": value, "as_of": "2026-09-24", "unit": "%", "source": mid,
            "source_url": None, "captured_at": "2026-09-24T19:45:00+00:00", "quality": "verified",
            "date_basis": "writer_confirmation", "evidence": "html_labeled_value",
            "dependencies": [], "release_status": "unknown"}


def corridor(**changes_by_id):
    return EconDeltaSnapshot(NOW, POLLED_UPSTREAM, dict(CORRIDOR),
        {mid: {**confirmation(mid, value), **changes_by_id.get(mid, {})} for mid, value in CORRIDOR.items()},
        write_status=RECEIPTS)


def test_legitimate_corridor_confirmations_neither_hold_nor_degrade():
    result = assess(corridor(), persisted_rows=[], now=NOW)
    assert (result.state, result.reasons, result.unavailable) == ("ready", (), ())


def test_held_corridor_confirmation_degrades_and_is_named_a_confirmation_date():
    result = assess(corridor(policy_rate_sdf={"quality": "held", "as_of": "2026-09-20",
                                              "captured_at": "2026-09-20T19:45:00+00:00"}),
                    persisted_rows=[], now=NOW)
    assert result.state == "degraded"
    (reason,) = result.reasons
    assert "policy_rate_sdf" in reason and "2026-09-20" in reason
    assert "confirmation date" in reason
    assert "held reading from" not in reason  # the dated-observation wording


def test_held_confirmation_recovered_from_a_legacy_archive_is_not_a_contradiction():
    # EconDelta's legacy-archive recovery (utils/opus_review.load_history) keeps
    # the archived source_as_of, which can precede that archive's capture time.
    result = assess(corridor(policy_rate_repo={"quality": "held", "as_of": "2026-08-29",
                                               "captured_at": "2026-08-30T20:55:00+00:00"}),
                    persisted_rows=[], now=NOW)
    assert result.state == "degraded"


def test_builder_corridor_date_is_never_compared_with_the_confirmation_date():
    from brief.builders.bb import _LAST_MPC_DECISION
    from brief.schema import Metric
    rows = [Metric(id=mid, label=mid, value=value, unit="%", source="BB", as_of=_LAST_MPC_DECISION,
                   cadence="event") for mid, value in CORRIDOR.items()]
    assert assess(corridor(), persisted_rows=rows, now=NOW).state == "ready"


def test_restamped_quote_outside_the_corridor_still_holds():
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {"quote": 80}, {"quote": {**OBS, "as_of": "2026-09-25",
        "date_basis": "writer_confirmation"}}, write_status=RECEIPTS)
    result = assess(snap, persisted_rows=[], now=NOW)
    assert result.state == "hold"
    assert any(reason.startswith("quote:") for reason in result.reasons)


@pytest.mark.parametrize("changes", [
    {"value": 9.25},
    {"as_of": "2026-09-26", "captured_at": "2026-09-26T01:00:00+00:00"},
    {"as_of": "2026-09-25"},
    {"evidence": ""},
    {"source": ""},
    {"captured_at": "2026-09-24T19:45:00"},
    {"metric_id": "policy_rate_slf"},
], ids=["value-mismatch", "future-date", "after-capture-date", "missing-evidence",
        "missing-source", "naive-capture", "wrong-metric-id"])
def test_corridor_confirmation_failing_integrity_still_holds(changes):
    result = assess(corridor(policy_rate_repo=changes), persisted_rows=[], now=NOW)
    assert result.state == "hold"
    assert any(reason.startswith("policy_rate_repo:") for reason in result.reasons)


# ── Builder card vs accepted record: FX, oil and a monthly metric must still hold ──
from brief.schema import Metric  # noqa: E402

FX = dict(OBS, metric_id="usd_bdt_mid", value=122.99, unit="BDT", as_of="2026-09-24", source="bb_forex")
OIL = dict(OBS, metric_id="brent_crude_usd_barrel", value=98.32, unit="USD/barrel", source="commodity_prices")
BANK = dict(OBS, metric_id="fiscal_bank_borrow_trn", value=1.66, unit="BDT trillion", as_of="2026-06-30",
            source="bank_borrowing_for_deficit_financing")
CARDS = {  # card as its builder prints the record above
    "usd_bdt_mid": Metric(id="fx_usd_bdt_mid", label="USD/BDT mid", value=122.99, unit="BDT",
                          as_of=date(2026, 9, 24), source="bb_forex", cadence="daily"),
    "brent_crude_usd_barrel": Metric(id="iranwar_brent_spot", label="Brent spot", value=98.32, unit="USD/bbl",
                                     as_of=date(2026, 9, 23), source="commodity_prices", cadence="daily"),
    "fiscal_bank_borrow_trn": Metric(id="fiscal_govt_borrow_trn", label="Govt bank borrow YTD", value=1.66,
                                     unit="BDT trn", as_of=date(2026, 6, 30), source="BB", cadence="monthly"),
}


def bound(record, card):
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {record["metric_id"]: record["value"]}, {record["metric_id"]: record},
                             write_status=RECEIPTS)
    return assess(snap, persisted_rows=[card], now=NOW)


@pytest.mark.parametrize("record", [FX, OIL, BANK], ids=["fx", "oil", "monthly"])
def test_a_card_printing_its_accepted_record_is_ready(record):
    assert bound(record, CARDS[record["metric_id"]]).state == "ready"


@pytest.mark.parametrize("field,altered", [("value", 1.67), ("as_of", date(2026, 6, 29)),
                                           ("unit", "BDT crore"), ("source", "NBR")])
@pytest.mark.parametrize("record", [FX, OIL, BANK], ids=["fx", "oil", "monthly"])
def test_a_card_departing_from_its_accepted_record_holds(record, field, altered):
    card = CARDS[record["metric_id"]].model_copy(update={field: altered})
    result = bound(record, card)
    assert result.state == "hold"
    assert result.reasons[0] == f"{record['metric_id']}: builder and accepted observation disagree"


@pytest.mark.parametrize("record", [FX, OIL, BANK], ids=["fx", "oil", "monthly"])
def test_a_different_producer_source_holds_even_under_a_known_label(record):
    result = bound(dict(record, source="archive"), CARDS[record["metric_id"]])
    assert result.state == "hold"


def test_the_bank_only_card_is_not_compared_with_total_domestic_borrowing():
    """fiscal.py kept the public id fiscal_govt_borrow_trn but reads bank-only borrowing; the
    snapshot's own fiscal_govt_borrow_trn is total domestic borrowing (another concept)."""
    domestic = dict(BANK, metric_id="fiscal_govt_borrow_trn", value=1.65,
                    source="domestic_borrowing_for_budget_deficit")
    card = CARDS["fiscal_bank_borrow_trn"]
    snap = EconDeltaSnapshot(NOW, POLLED_UPSTREAM, {"fiscal_govt_borrow_trn": 1.65, "fiscal_bank_borrow_trn": 1.66},
                             {"fiscal_govt_borrow_trn": domestic, "fiscal_bank_borrow_trn": BANK},
                             write_status=RECEIPTS)
    assert assess(snap, persisted_rows=[card], now=NOW).state == "ready"
    printing_domestic = card.model_copy(update={"value": 1.65})
    result = assess(snap, persisted_rows=[printing_domestic], now=NOW)
    assert result.reasons == ("fiscal_bank_borrow_trn: builder and accepted observation disagree",)


# ── Remittance: the flash, or an independently dated official final that remit.py prefers ──
FLASH = dict(OBS, metric_id="remit_monthly_mn", value=2970.0, unit="USD million", as_of="2026-08-31",
             source="monthly_remittance", release_status="provisional")


def remittance(card_value, card_date, status, publisher="BB", **flash):
    card = Metric(id="remit_monthly_mn", label="Monthly Remittance", value=card_value, unit="mn USD",
                  as_of=card_date, source=f"{publisher} · {card_date:%b %Y}, {status}", cadence="monthly")
    return bound(dict(FLASH, **flash), card)


@pytest.mark.parametrize("card,flash", [
    ((2970.0, date(2026, 8, 31), "provisional"), {}),                       # the flash itself
    ((2970.0, date(2026, 8, 31), "final"), {"release_status": "final"}),    # a final flash
    ((2981.4, date(2026, 8, 1), "final"), {}),                             # same-month final beats a flash
    ((2981.4, date(2026, 8, 1), "final"), {"as_of": "2026-07-31"}),       # newer official month
    ((2858.68, date(2026, 7, 1), "final"), {"release_status": "unknown"}),  # flash not a builder candidate
    ((2858.68, date(2026, 7, 1), "final"), {"unit": "USD billion", "value": 2.97}),
], ids=["flash", "final-flash", "same-month-final", "newer-final", "unmarked-flash", "flash-in-billions"])
def test_remittance_cards_that_remit_py_legitimately_selects_are_not_held(card, flash):
    result = remittance(*card, **flash)  # a provisional flash still degrades, honestly
    assert result.state != "hold"
    assert not [reason for reason in result.reasons if "disagree" in reason]


@pytest.mark.parametrize("card,flash", [
    ((2970.0, date(2026, 8, 31), "provisional"), {"source": "archive"}),     # another producer's number
    ((2971.0, date(2026, 8, 31), "provisional"), {}),                       # altered value
    ((2970.0, date(2026, 8, 30), "provisional"), {}),                       # altered date
    ((2858.68, date(2026, 7, 1), "final"), {}),                             # older final over a newer flash
    ((2981.4, date(2026, 8, 1), "final"), {"release_status": "final"}),     # two finals, one month
    # remit.py never prints an unmarked flash, and prints a final flash as final: an invented status
    ((2970.0, date(2026, 8, 31), "provisional"), {"release_status": "unknown"}),
    ((2970.0, date(2026, 8, 31), "provisional"), {"release_status": "final"}),
    # remit.py always names BB: the right figure under another publisher is not its card
    ((2970.0, date(2026, 8, 31), "provisional", "The Daily Star"), {}),
    ((2858.68, date(2026, 7, 1), "final", "The Daily Star"), {"release_status": "unknown"}),
    ((2981.4, date(2026, 8, 1), "final", "The Daily Star"), {"as_of": "2026-07-31"}),
], ids=["other-source", "value", "date", "older-final", "conflicting-finals",
        "unmarked-flash-called-provisional", "final-flash-called-provisional",
        "flash-under-another-publisher", "final-under-another-publisher", "newer-final-under-another-publisher"])
def test_remittance_cards_remit_py_would_not_select_hold(card, flash):
    result = remittance(*card, **flash)
    assert result.state == "hold"
    assert result.reasons[0] == "remit_monthly_mn: builder and accepted observation disagree"


# ── Malformed receipts hold; absent receipts stay unconfirmed; nothing crashes ──
def receipted(write_status, **snapshot_fields):
    fields = {"sources_status": POLLED_UPSTREAM, "data": {"quote": 80}, "observations": {"quote": OBS}}
    return EconDeltaSnapshot(NOW, **{**fields, **snapshot_fields}, write_status=write_status)


@pytest.mark.parametrize("write_status", [["ok"], "ok", 1, True], ids=["list", "string", "number", "bool"])
def test_a_write_status_that_is_not_an_object_holds_as_a_malformed_receipt(write_status):
    result = assess(receipted(write_status), persisted_rows=[], now=NOW)
    assert result.state == "hold"
    assert "persistence receipts malformed" in result.reasons[0]


@pytest.mark.parametrize("stage", ["daily", "monthly"])
@pytest.mark.parametrize("receipt", ["ok", ["ok"], None, 1], ids=["string", "list", "null", "number"])
def test_a_stage_receipt_that_is_not_an_object_holds_rather_than_reading_as_absent(stage, receipt):
    result = assess(receipted({**RECEIPTS, stage: receipt}), persisted_rows=[], now=NOW)
    assert result.state == "hold"
    assert result.reasons == (f"{stage} persistence receipt malformed",)


@pytest.mark.parametrize("stage", ["daily", "monthly"])
def test_an_absent_stage_receipt_is_unconfirmed_not_malformed(stage):
    present = {k: v for k, v in RECEIPTS.items() if k != stage}
    result = assess(receipted(present), persisted_rows=[], now=NOW)
    assert (result.state, result.reasons) == ("degraded", (f"{stage} persistence unconfirmed (no receipt)",))


@pytest.mark.parametrize("changes", [
    {"status": "OK"}, {"status": None}, {"status": 1}, {"status": ["ok"]}, {"status": {"ok": True}},
    {"status": ""}, {"attempted_at": None}, {"attempted_at": 1727222160},
    {"attempted_at": "2026-09-25T02:00:00"}, {"attempted_at": "2026-09-25T04:00:00+00:00"},
], ids=["upper-case", "null-status", "number-status", "list-status", "object-status", "blank-status",
        "null-time", "epoch-time", "naive-time", "future-time"])
def test_an_invalid_nested_receipt_holds(changes):
    result = assess(receipted({**RECEIPTS, "daily": {**RECEIPTS["daily"], **changes}}),
                    persisted_rows=[], now=NOW)
    assert (result.state, result.reasons) == ("hold", ("daily persistence receipt malformed",))


@pytest.mark.parametrize("entry", [None, "ok", ["ok"], 1], ids=["null", "string", "list", "number"])
def test_a_malformed_source_status_entry_is_unknown_upstream_health(entry):
    result = assess(receipted(RECEIPTS, sources_status={**POLLED_UPSTREAM, "cpi": entry}), persisted_rows=[], now=NOW)
    assert (result.state, result.reasons) == ("degraded", ("source cpi: unknown (malformed status entry)",))


@pytest.mark.parametrize("metadata", ["verified", ["quote"], None, 80], ids=["string", "list", "null", "number"])
def test_non_object_observation_metadata_is_an_identity_contradiction(metadata):
    result = assess(receipted(RECEIPTS, observations={"quote": metadata}), persisted_rows=[], now=NOW)
    assert (result.state, result.reasons) == ("hold", ("quote: inconsistent observation identity/value/date/evidence",))


def test_an_unhashable_observation_unit_is_a_disagreement_not_a_crash():
    card = Metric(id="quote", label="Quote", value=80, unit="USD/barrel", source="official",
                  as_of=date(2026, 9, 23), cadence="daily")
    snap = receipted(RECEIPTS, observations={"quote": {**OBS, "unit": ["USD/barrel"]}})
    result = assess(snap, persisted_rows=[card], now=NOW)
    assert (result.state, result.reasons) == ("hold", ("quote: builder and accepted observation disagree",))


# ── Missing, truncated and old snapshots are never read as fresh ──
def test_an_unavailable_snapshot_has_no_capture_time_and_is_reported_not_ready():
    snap = EconDeltaSnapshot.unavailable("EconDelta snapshot not found: /data/latest.json")
    assert snap.updated_at is None and snap.data == {} and snap.write_status is None
    result = assess(snap, persisted_rows=[], now=NOW)
    assert result.state == "degraded"
    assert result.reasons[0] == ("EconDelta snapshot unavailable (EconDelta snapshot not found: "
                                 "/data/latest.json): capture time, source health and accepted "
                                 "observations unknown")


def test_a_snapshot_without_a_capture_time_is_never_ready():
    snap = EconDeltaSnapshot(None, POLLED_UPSTREAM, {"quote": 80}, {"quote": OBS}, write_status=RECEIPTS)
    result = assess(snap, persisted_rows=[], now=NOW)
    assert (result.state, result.reasons) == ("degraded", ("snapshot capture time unknown",))


def test_an_old_snapshot_with_perfect_receipts_is_degraded_by_its_age():
    from datetime import timedelta
    snap = EconDeltaSnapshot(NOW - timedelta(days=3), POLLED_UPSTREAM, {"quote": 80}, {"quote": OBS}, write_status=RECEIPTS)
    result = assess(snap, persisted_rows=[], now=NOW)
    assert (result.state, result.reasons) == ("degraded", ("snapshot capture is more than one day old",))


# ── Owner decision (e): readiness names WHY the snapshot is not a current capture, as a fixed
# category the CLI turns into one operator alert. A hold carries none (the failure unit alerts). ──
def test_the_snapshot_problem_is_the_load_cause_of_an_unavailable_snapshot():
    snap = EconDeltaSnapshot.unavailable("EconDelta snapshot unparseable: /data/latest.json: x",
                                         cause="truncated")
    result = assess(snap, persisted_rows=[], now=NOW)
    assert (result.state, result.snapshot_problem) == ("degraded", "truncated")


def test_an_unavailable_snapshot_without_a_known_cause_is_still_a_snapshot_problem():
    result = assess(EconDeltaSnapshot.unavailable("unknown"), persisted_rows=[], now=NOW)
    assert (result.state, result.snapshot_problem) == ("degraded", "unavailable")


def test_an_old_capture_is_a_stale_capture_problem():
    from datetime import timedelta
    snap = EconDeltaSnapshot(NOW - timedelta(days=1, seconds=1), POLLED_UPSTREAM, {}, write_status=RECEIPTS)
    result = assess(snap, persisted_rows=[], now=NOW)
    assert (result.state, result.snapshot_problem) == ("degraded", "stale capture")


def test_a_capture_within_one_day_is_no_snapshot_problem():
    from datetime import timedelta
    # 03:00 BDT capture read at 09:00 BDT: within one day AND on the same Bangladesh day
    # (R2 fix 9 r1: a capture from an earlier Bangladesh day is its own snapshot problem).
    snap = EconDeltaSnapshot(NOW - timedelta(hours=6), POLLED_UPSTREAM, {}, write_status=RECEIPTS)
    assert assess(snap, persisted_rows=[], now=NOW).snapshot_problem is None


def test_a_capture_exactly_one_day_old_is_yesterdays_capture_not_a_stale_one():
    """The one-day age bound stays strict (> 24 h is "stale capture"); a capture exactly
    24 h old is still no longer today's capture on the Dhaka calendar."""
    from datetime import timedelta
    snap = EconDeltaSnapshot(NOW - timedelta(days=1), POLLED_UPSTREAM, {}, write_status=RECEIPTS)
    result = assess(snap, persisted_rows=[], now=NOW)
    assert (result.state, result.reasons, result.snapshot_problem) == (
        "degraded", ("snapshot capture is from an earlier Bangladesh day (2026-09-24 BDT)",),
        "earlier-day capture")


def test_a_capture_without_a_time_is_a_snapshot_problem():
    snap = EconDeltaSnapshot(None, POLLED_UPSTREAM, {}, write_status=RECEIPTS)
    assert assess(snap, persisted_rows=[], now=NOW).snapshot_problem == "capture time unknown"


def test_a_future_capture_holds_and_leaves_no_snapshot_problem_to_alert():
    from datetime import timedelta
    snap = EconDeltaSnapshot(NOW + timedelta(minutes=5), POLLED_UPSTREAM, {}, write_status=RECEIPTS)
    result = assess(snap, persisted_rows=[], now=NOW)
    assert (result.state, result.snapshot_problem) == ("hold", None)
