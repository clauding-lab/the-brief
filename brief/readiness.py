"""Publication readiness from the exact gathered inputs, without database I/O.

Write confirmation and source freshness are independent: a successful database
read cannot establish that an upstream source was polled successfully.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Iterator, Literal

# The Brief's monthly month-end convention (P0 honesty fix #204).
from brief.cadence import month_end
from brief.econdelta import (
    _DHAKA,  # the Dhaka calendar EconDelta's captures are dated in
    EconDeltaSnapshot,
    WriterConfirmation,
)
from brief.schema import Metric

# Builder card id -> the accepted record (snapshot id) that card displays, where they differ.
_CARD_RECORD: dict[str, str] = {
    "iranwar_brent_spot": "brent_crude_usd_barrel", "iranwar_wti_spot": "wti_crude_usd_barrel",
    "fx_gold_usd_oz": "gold_usd_oz", "fx_usd_bdt_mid": "usd_bdt_mid",
    # fiscal.py kept this public id when the card was corrected to BANK-only borrowing
    # (its read_id, and pipeline._enrich_metric_history's read_ids). The snapshot's own
    # fiscal_govt_borrow_trn is total DOMESTIC borrowing: a different concept.
    "fiscal_govt_borrow_trn": "fiscal_bank_borrow_trn",
}
# Two spellings of one unit; never a scale change.
_SAME_UNIT: dict[str, str] = {"USD/bbl": "USD/barrel", "mn USD": "USD million",
                              "BDT trn": "BDT trillion"}  # fiscal.py's unit string (landmine 34)
# Accepted record id -> (the static label its builder prints, the one EconDelta source it names).
_BUILDER_LABEL: dict[str, tuple[str, str]] = {
    "dsex": ("DSE", "dse_market"),  # dse.py labels EconDelta's DSE market scrape "DSE"
    **{mid: ("BB", "auction_results") for mid in (  # tbond.py: BB auction cut-offs
        "tbond_tbill_91d", "tbond_tbill_182d", "tbond_tbill_364d", "tbond_bond_5y", "tbond_bond_10y")},
    "banking_npl_pct": ("BB", "gross_npl_ratio"),  # banking.py: BB Financial Stability Report
    "banking_car_pct": ("BB", "banking_sector_crar"),
    "fiscal_nbr_collected_trn": ("NBR", "tax_revenue"),  # fiscal.py: WSEI "Tax Revenue (NBR)"
    "fiscal_bank_borrow_trn": ("BB", "bank_borrowing_for_deficit_financing"),  # fiscal.py: MEI
}
_STAGES = ("daily", "monthly")
_RECEIPT_STATUSES = ("ok", "failed", "skipped")
# EconDelta's approved-press re-assertion (R2 fix 10). Its own stage: the card it feeds is
# checked against the row its builder actually read (_press_card_matches), so a problem
# persisting it degrades; it is never charged to the daily write and never read as success.
_OVERRIDE_STAGE = "media_overrides"
# Required text fields of one failure / skip entry (EconDelta utils/schema.py ReceiptFailure/Skip).
_ENTRY_FIELDS = {"failures": ("operation", "category", "detail"), "skips": ("category", "detail")}
_MALFORMED_SOURCE = "unknown (malformed status entry)"
# EconDelta's upstream CPI/M2 source-poll liveness (R2 fix 5; shared contract
# upstream_liveness_contract.families): sources_status key -> family label. Required: an
# absent entry is unknown liveness, never a polled job.
_UPSTREAM_FAMILIES: dict[str, str] = {"cpi_upstream_poll": "CPI", "m2_upstream_poll": "M2"}
# Derived monthly leg -> the liveness entry that vouches for it (same contract, families[*].monthly_leg).
_DERIVED_LEG_POLL: dict[str, str] = {"cpi": "cpi_upstream_poll", "m2": "m2_upstream_poll"}
# How old an EconDelta capture may be before it is a "stale capture". There is no separate
# accepted capture-age policy; this is EconDelta's own daily collection-age threshold
# (aggregate_latest.STALE_THRESHOLDS_HOURS_BY_CADENCE["daily"] = 24 h, the collection-age tier
# ruling E1 names), matching its once-a-day 02:55 BDT aggregate timer (EconDelta landmine 42).
_CAPTURE_MAX_AGE = timedelta(hours=24)
_WENT_BACKWARDS = "capture went backwards"  # older than the newest capture a live run read
# Monthly leg skip categories (EconDelta utils/write_receipts.py) that can be healthy lag.
_OFFICIAL_LAG = "no new official period"         # a source leg read BB's own publication listing
_DATABASE_VINTAGE = "no newer database vintage"  # a derived leg reread our own daily table
# The lag window is the one EconDelta states with each lag (skip field lag_window_days): its
# sentinel vintage grace for that series' cadence (ruling E1; e.g. remittance "monthly" 45 days,
# imports "quarterly" 165 days for BB's ~2-month MEI lag), counted here from the month's end.
# No window of the Brief's own: one series' lag is not another's.
# remit.py prints the WSEI remittance flash as "BB · <Mon YYYY>, <release status>".
_REMITTANCE, _REMITTANCE_SOURCE, _REMITTANCE_PREFIX = "remit_monthly_mn", "monthly_remittance", "BB · "


@dataclass(frozen=True)
class Readiness:
    state: Literal["ready", "degraded", "hold"]
    reasons: tuple[str, ...]
    unavailable: tuple[str, ...] = ()
    # Why the snapshot itself could not be trusted as a current capture (owner decision (e)):
    # a load cause from brief.econdelta.UNAVAILABLE_CAUSES, "stale capture",
    # "earlier-day capture", "capture went backwards", "capture time unknown", or None.
    snapshot_problem: str | None = None
    # Healthy, informational facts that never degrade (fix 4: official BB publication lag).
    notes: tuple[str, ...] = ()


def assess(snapshot: EconDeltaSnapshot, *, persisted_rows: Iterable[Metric], now: datetime,
           last_capture: datetime | None = None) -> Readiness:
    """Assess accepted observations against already gathered, dated metrics.

    Legacy snapshots remain usable with independent dated evidence; absence of
    write receipts never becomes an invented successful write. `last_capture` is the
    newest capture a live run already read and passed readiness with (brief.capture_mark;
    recorded before run_publish, so not proof of a publish), or None when unknown.
    """
    reasons: list[str] = []
    contradictions: list[str] = []
    unavailable: list[str] = []
    notes: list[str] = []
    rows = {_CARD_RECORD.get(row.id, row.id): row for row in persisted_rows}
    snapshot_problem = _judge_capture(snapshot, now, contradictions, reasons, last_capture)
    _judge_receipts(snapshot, now, contradictions, reasons, notes)
    for source, entry in snapshot.sources_status.items():
        status = entry.get("status", "unknown") if isinstance(entry, dict) else _MALFORMED_SOURCE
        if status != "ok":
            reasons.append(_source_reason(source, status, entry))
    reasons.extend(_unreported_upstream(snapshot))
    for mid in snapshot.data:
        confirmation = snapshot.writer_confirmation(mid, today=now.date())
        if confirmation is not None:
            # Writer liveness for a standing corridor rate: never an observation
            # date, so it is never compared with a builder's as_of (landmine 24).
            if confirmation.quality == "held":
                reasons.append(_held_confirmation_reason(confirmation))
            continue
        obs = snapshot.observation(mid, today=now.date())
        if mid in snapshot.observations and obs is None:
            metadata = snapshot.observations[mid]
            if isinstance(metadata, dict) and metadata.get("quality") == "unavailable":
                unavailable.append(mid)
            else:
                contradictions.append(f"{mid}: inconsistent observation identity/value/date/evidence")
            continue
        row = rows.get(mid)
        if obs is None:
            if row is None or row.value is None or row.as_of > now.date() or not row.source:
                unavailable.append(mid)
            continue
        if obs["quality"] == "held":
            reasons.append(f"{mid}: held reading from {obs['as_of']}")
        if obs.get("release_status") == "provisional":
            reasons.append(f"{mid}: provisional reading from {obs['as_of']}")
        if row is not None and not _card_matches(mid, row, obs):
            contradictions.append(f"{mid}: builder and accepted observation disagree")
    if unavailable:
        reasons.append("unknown current readings unavailable: " + ", ".join(sorted(unavailable)))
    return Readiness("hold" if contradictions else "degraded" if reasons else "ready",
                     tuple(contradictions + reasons), tuple(sorted(unavailable)), snapshot_problem,
                     tuple(notes))


def _source_reason(source: str, status: Any, entry: Any) -> str:
    """Carry the producer's own explanation, e.g. EconDelta's upstream CPI/M2 source-poll
    liveness (R2 fix 5): a database reread is not an upstream poll, and the log says so."""
    error = entry.get("error") if isinstance(entry, dict) else None
    return f"source {source}: {status}" + (f" ({error})" if isinstance(error, str) and error else "")


def _unreported_upstream(snapshot: EconDeltaSnapshot) -> list[str]:
    """A CPI/M2 liveness entry the snapshot does not carry (a pre-fix-5 producer, or one that
    drops a key) is unknown, never a polled job: it degrades like an absent write receipt."""
    return [f"source {key}: missing ({label} upstream source-poll liveness not reported by "
            "EconDelta (no entry in sources_status))"
            for key, label in _UPSTREAM_FAMILIES.items() if key not in snapshot.sources_status]


def _judge_capture(snapshot: EconDeltaSnapshot, now: datetime, contradictions: list[str],
                   reasons: list[str], last_capture: datetime | None = None) -> str | None:
    """An unreadable snapshot or an unknown capture time is reported, never read as fresh.

    Returns the snapshot problem category for a degraded capture; None when the capture is
    current or is a contradiction (a hold, which alerts through the failure unit instead).
    """
    if snapshot.load_error is not None:
        reasons.append(f"EconDelta snapshot unavailable ({snapshot.load_error}): capture time, "
                       "source health and accepted observations unknown")
        return snapshot.load_cause or "unavailable"
    if snapshot.updated_at is None:
        reasons.append("snapshot capture time unknown")
        return "capture time unknown"
    if snapshot.updated_at.utcoffset() is None or snapshot.updated_at > now:
        contradictions.append("snapshot capture time is invalid or in the future")
        return None
    # The pull copies whatever ExonVPS holds, with no capture-time check (R2 task G3): a
    # restored older snapshot is named for what it is. Degraded, never held (decision (e)):
    # its records are still dated and checked one by one below; it is no worse than a
    # missing snapshot, which publishes degraded. Its age, if also old, is still stated.
    went_backwards = False
    if last_capture is not None and snapshot.updated_at < last_capture:
        went_backwards = True
        reasons.append(f"snapshot capture went backwards ({_bdt(snapshot.updated_at)} is older than "
                       f"{_bdt(last_capture)}, already read by a live run that passed readiness)")
    age_problem = _judge_capture_age(snapshot.updated_at, now, reasons)
    return _WENT_BACKWARDS if went_backwards else age_problem


def _bdt(instant: datetime) -> str:
    return instant.astimezone(_DHAKA).strftime("%Y-%m-%d %H:%M:%S BDT")


def _judge_capture_age(captured: datetime, now: datetime, reasons: list[str]) -> str | None:
    if now - captured > _CAPTURE_MAX_AGE:
        reasons.append("snapshot capture is more than one day old")
        return "stale capture"
    captured_on = captured.astimezone(_DHAKA).date()
    if captured_on < now.astimezone(_DHAKA).date():
        # Under a day old yet not today's: an off-schedule capture (manual run, or a catch-up
        # fire of EconDelta's Persistent timer) retained through a held or missed night. The
        # Brief does not read EconDelta's latest.attempt.json, so the capture day must say it.
        reasons.append(f"snapshot capture is from an earlier Bangladesh day ({captured_on.isoformat()} BDT)")
        return "earlier-day capture"
    return None


def _judge_receipts(snapshot: EconDeltaSnapshot, now: datetime, contradictions: list[str],
                    reasons: list[str], notes: list[str]) -> None:
    """Absent receipts stay unconfirmed; a present but malformed receipt is a contradiction."""
    write_status = snapshot.write_status
    if write_status is not None and not isinstance(write_status, dict):
        contradictions.append("persistence receipts malformed (write_status is not an object)")
        return
    for stage in _STAGES:
        if write_status is None or stage not in write_status:
            reasons.append(f"{stage} persistence unconfirmed (no receipt)")
            continue
        receipt = write_status[stage]
        if not _well_formed_receipt(receipt, now):
            contradictions.append(f"{stage} persistence receipt malformed")
        elif receipt["status"] == "failed":
            contradictions.append(f"{stage} persistence failed: {receipt.get('reason', 'unconfirmed write')}")
        elif stage == "monthly" and receipt.get("legs"):
            _judge_monthly_legs(receipt, snapshot.sources_status, now, reasons, notes)
        elif receipt["status"] == "skipped":
            reasons.append(f"{stage} persistence skipped: {receipt.get('reason', 'not attempted')}")
    if write_status is not None and _OVERRIDE_STAGE in write_status:
        _judge_override_receipt(write_status[_OVERRIDE_STAGE], now, contradictions, reasons)


def _judge_monthly_legs(receipt: dict, sources_status: dict[str, Any], now: datetime,
                        reasons: list[str], notes: list[str]) -> None:
    """R2 fix 4: every leg that wrote nothing is judged by why, even beside a leg that
    confirmed rows. Only official BB lag is healthy; the rest degrades (log-only, no hold)."""
    today = now.astimezone(_DHAKA).date()
    for name, leg in _leaf_legs(receipt, "monthly"):
        skips = leg.get("skips") or []
        if leg["status"] == "skipped" and not skips:
            reasons.append(f"monthly {name} leg skipped: reason not itemised")
        for skip in skips:
            healthy, text = _judge_leg_skip(name, skip, sources_status, today)
            (notes if healthy else reasons).append(text)


def _leaf_legs(receipt: dict, name: str) -> Iterator[tuple[str, dict]]:
    legs = receipt.get("legs") or {}
    if not legs:
        yield name, receipt
    for child_name, child in legs.items():
        yield from _leaf_legs(child, child_name)


def _judge_leg_skip(leg: str, skip: dict, sources_status: dict[str, Any],
                    today: date) -> tuple[bool, str]:
    """(healthy, text). An unknown category is never healthy."""
    if skip["category"] == _OFFICIAL_LAG:
        return _judge_official_lag(leg, skip, today)
    if skip["category"] == _DATABASE_VINTAGE:
        return _judge_database_vintage(leg, sources_status)
    return False, f"monthly {leg} leg: {skip['category']}: {skip['detail']}"


def _judge_official_lag(leg: str, skip: dict, today: date) -> tuple[bool, str]:
    """BB's own listing has nothing newer: healthy while its newest stored month is inside the
    lag window EconDelta accepts for that series."""
    month = _recorded_month(skip.get("newest_recorded"), today)
    if month is None:
        return False, (f"monthly {leg} leg: {_OFFICIAL_LAG}, but no verifiable newest recorded "
                       "month (lag window cannot be checked)")
    window = _lag_window(skip.get("lag_window_days"))
    if window is None:
        return False, (f"monthly {leg} leg: {_OFFICIAL_LAG}, but no accepted lag window reported "
                       "(lag window cannot be checked)")
    if (today - month_end(month)).days > window:
        return False, (f"monthly {leg} leg: {_OFFICIAL_LAG}, but its newest recorded month "
                       f"{month.isoformat()} is past its accepted {window}-day lag window "
                       "(stale since BB published nothing newer)")
    return True, (f"monthly {leg} leg: official publication lag (BB lists nothing after "
                  f"{month:%Y-%m}; inside its accepted {window}-day lag window)")


def _lag_window(raw: Any) -> int | None:
    """A whole, positive number of days (never a bool); anything else is unverifiable (None)."""
    return raw if type(raw) is int and raw > 0 else None


def _recorded_month(raw: Any, today: date) -> date | None:
    """An ISO date not after today; absent, malformed or future is unverifiable (None)."""
    if not isinstance(raw, str):
        return None
    try:
        month = date.fromisoformat(raw)
    except ValueError:
        return None
    return month if month <= today else None


def _judge_database_vintage(leg: str, sources_status: dict[str, Any]) -> tuple[bool, str]:
    """Our own table holding nothing newer says nothing about BB unless the family's upstream
    source poll (R2 fix 5) is ok."""
    key = _DERIVED_LEG_POLL.get(leg)
    if key is None:
        return False, (f"monthly {leg} leg: {_DATABASE_VINTAGE}, and no upstream source poll vouches "
                       "for this leg (a database reread cannot show BB publication lag)")
    entry, label = sources_status.get(key), _UPSTREAM_FAMILIES[key]
    status = (entry.get("status", "unknown") if isinstance(entry, dict)
              else "not reported" if entry is None else _MALFORMED_SOURCE)
    if status == "ok":
        return True, f"monthly {leg} leg: {_DATABASE_VINTAGE}; {label} upstream source poll ok"
    return False, (f"monthly {leg} leg: {_DATABASE_VINTAGE}, and {label} upstream source-poll "
                   f"liveness is {status} (a database reread cannot show BB publication lag)")


def _judge_override_receipt(receipt: Any, now: datetime,
                            contradictions: list[str], reasons: list[str]) -> None:
    """Absent (a pre-fix-10 producer) or skipped (nothing to send) adds nothing."""
    if not _well_formed_receipt(receipt, now):
        contradictions.append(f"{_OVERRIDE_STAGE} persistence receipt malformed")
    elif receipt["status"] == "failed":
        reasons.append("approved press override persistence failed: "
                       f"{receipt.get('reason') or 'unconfirmed write'}")


def _well_formed_receipt(receipt: Any, now: datetime) -> bool:
    """EconDelta's WriteReceipt contract, all the way down its legs.

    Unknown additive fields are ignored (a newer producer must not hold an older reader);
    a known field of the wrong type, or a status its own evidence contradicts, is malformed.
    """
    if not isinstance(receipt, dict) or not isinstance(receipt.get("status"), str):
        return False
    try:
        attempted = datetime.fromisoformat(receipt["attempted_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    return (receipt["status"] in _RECEIPT_STATUSES
            and attempted.utcoffset() is not None and attempted <= now
            and _optional_fields_typed(receipt)
            and all(_well_formed_receipt(leg, now) for leg in (receipt.get("legs") or {}).values())
            and _status_agrees_with_evidence(receipt))


def _optional_fields_typed(receipt: dict) -> bool:
    rows, legs = receipt.get("confirmed_rows"), receipt.get("legs")
    return (receipt.get("reason") is None or isinstance(receipt["reason"], str)) \
        and (rows is None or (type(rows) is int and rows >= 0)) \
        and (legs is None or isinstance(legs, dict)) \
        and all(_entries_typed(receipt.get(name), fields) for name, fields in _ENTRY_FIELDS.items())


def _entries_typed(entries: Any, fields: tuple[str, ...]) -> bool:
    return entries is None or (isinstance(entries, list) and all(
        isinstance(e, dict) and all(isinstance(e.get(f), str) for f in fields) for e in entries))


def _status_agrees_with_evidence(receipt: dict) -> bool:
    """A failure is never reported healthier than it is, at any level (failure dominates)."""
    status, failures, rows = receipt["status"], receipt.get("failures"), receipt.get("confirmed_rows")
    if failures and status != "failed":
        return False
    if failures is not None and rows is not None \
            and status != ("failed" if failures else "ok" if rows else "skipped"):
        return False
    legs = list((receipt.get("legs") or {}).values())
    if not legs:
        return True
    states = {leg["status"] for leg in legs}
    implied = "failed" if "failed" in states else "ok" if "ok" in states else "skipped"
    return status == implied and (rows is None or rows == sum(leg.get("confirmed_rows") or 0 for leg in legs))


def _card_matches(mid: str, row: Metric, obs: dict[str, Any]) -> bool:
    """The card prints exactly the accepted record, the official final remit.py prefers, or
    the owner-approved press figure its builder read."""
    if row.press_override is not None:
        return _press_card_matches(row, obs)
    if mid == _REMITTANCE:
        flash = (obs["source"] == _REMITTANCE_SOURCE and row.source.startswith(_REMITTANCE_PREFIX)
                 and _remittance_status(row) == obs.get("release_status"))
        return (flash and _same_reading(row, obs)) or _remittance_final_selected(row, obs)
    source_ok = row.source == obs["source"] or (row.source, obs["source"]) == _BUILDER_LABEL.get(mid)
    return source_ok and _same_reading(row, obs)


def _press_card_matches(row: Metric, obs: dict[str, Any]) -> bool:
    """Owner decision (c): accept exactly the media-approved row the builder read (bound on
    the card, no second history read), printed under that outlet's name, in the accepted
    record's unit, and never older than the accepted record."""
    press = row.press_override
    return (row.source == press.card_source and row.value == press.value
            and row.as_of == press.as_of
            and _canonical_unit(row.unit) == _canonical_unit(obs.get("unit"))
            and press.as_of >= date.fromisoformat(obs["as_of"]))


def _same_reading(row: Metric, obs: dict[str, Any]) -> bool:
    return (row.value == obs["value"] and row.as_of.isoformat() == obs["as_of"]
            and _canonical_unit(row.unit) == _canonical_unit(obs.get("unit")))


def _canonical_unit(unit: Any) -> Any:
    """Fold spellings of one unit; a non-string unit is left to compare unequal."""
    return _SAME_UNIT.get(unit, unit) if isinstance(unit, str) else unit


def _remittance_status(row: Metric) -> str | None:
    return "final" if ", final" in row.source else "provisional" if ", provisional" in row.source else None


def _remittance_final_selected(row: Metric, obs: dict[str, Any]) -> bool:
    """remit.py: the newest evidenced month wins and a same-month official final beats the
    flash; the flash competes only with a known release status in USD million."""
    if not (row.source.startswith(_REMITTANCE_PREFIX) and _remittance_status(row) == "final"):
        return False
    flash = date.fromisoformat(obs["as_of"])
    card_month, flash_month = (row.as_of.year, row.as_of.month), (flash.year, flash.month)
    competes = obs.get("release_status") in ("final", "provisional") and obs.get("unit") == "USD million"
    return (not competes or card_month > flash_month
            or (card_month == flash_month and obs["release_status"] != "final"))


def _held_confirmation_reason(confirmation: WriterConfirmation) -> str:
    return (f"{confirmation.metric_id}: held standing rate; writer last confirmed it on "
            f"{confirmation.confirmed_on.isoformat()} (a confirmation date, not an "
            "observation or decision date)")
