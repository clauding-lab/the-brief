"""R2 fix H5 (owner decision m): the NBR card after EconDelta stops re-stamping the NBR total.

EconDelta's tests/test_nbr_fytd_period_rows.py proves its real producer makes the shared
contract's `r2_case_contract.nbr_fytd_period_rows`: five nights, each NBR row dated by the
source's own stated period and sent only when that (period, value) is new. Here the rows those
nights leave in metric_history, and the snapshot of that night, go through the real builders
and the readiness check. The card must print the last properly dated figure with its real
period date; readiness must never hold on it, and never call it fresh when it is not.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from brief.econdelta import load_snapshot
from brief.history import HistoryRow
from brief.readiness import assess
from tests.test_producer_consumer_contract import (
    BRIEF_RUN,
    contradictions,
    gathered_sections,
)
from tests.upstream_liveness import POLLED_UPSTREAM

CONTRACT = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json").read_text())
SEQUENCE = CONTRACT["r2_case_contract"]["nbr_fytd_period_rows"]
BINDING, CORRIDOR = CONTRACT["builder_binding_contract"], CONTRACT["writer_confirmation_contract"]
FAMILY = tuple(SEQUENCE["family"])
RUN_NAMES = [run["run"] for run in SEQUENCE["runs"]]


def night_after(tmp_path, run_name: str):
    """latest.json of that night (the real 25 Sep run with the NBR records it published, and its
    daily receipt with the skips it recorded) and every metric_history row sent through it."""
    runs = SEQUENCE["runs"][:RUN_NAMES.index(run_name) + 1]
    tonight = runs[-1]
    records = {**{mid: r["observation"] for mid, r in BINDING["records"].items()},
               **{r["expected"]["metric_id"]: r["expected"] for r in CORRIDOR["records"]},
               **tonight["observations"]}
    stored = [r["metric_history_row"] for r in [*BINDING["records"].values(), *CORRIDOR["records"]]
              if r["metric_history_row"] and r["metric_history_row"]["metric_id"] not in FAMILY]
    table = {(row["metric_id"], row["as_of"]): row for row in stored}
    for run in runs:  # last write wins on (metric_id, as_of), as the upsert does
        table.update({(row["metric_id"], row["as_of"]): row for row in run["rows_sent"].values()})
    daily = {"status": "ok", "attempted_at": BINDING["aggregate_captured_at"]}
    if tonight["daily_skips"]:
        daily["skips"] = tonight["daily_skips"]
    path = tmp_path / "latest.json"
    path.write_text(json.dumps({
        "updated_at": BINDING["aggregate_captured_at"],
        "sources_status": {**BINDING["sources_status"], **POLLED_UPSTREAM},
        "data": {mid: r["value"] for mid, r in records.items()}, "observations": records,
        "write_status": {"daily": daily, "monthly": {"status": "ok", "attempted_at": BINDING["aggregate_captured_at"]}}}))
    rows = [HistoryRow(r["metric_id"], date.fromisoformat(r["as_of"]), r["value"], r["source"])
            for r in table.values()]
    return load_snapshot(path), rows


def family_view(result) -> tuple[list[str], list[str]]:
    reasons = sorted(r for r in result.reasons if r.split(":")[0] in FAMILY)
    return reasons, sorted(mid for mid in result.unavailable if mid in FAMILY)


@pytest.mark.parametrize("check", SEQUENCE["brief_checks"], ids=[c["after_run"] for c in SEQUENCE["brief_checks"]])
def test_the_nbr_card_prints_the_last_properly_dated_figure_and_readiness_says_how_current_it_is(
        tmp_path, monkeypatch, check):
    snap, rows = night_after(tmp_path, check["after_run"])
    cards = {m.id: m for s in gathered_sections(monkeypatch, snap, rows) for m in s.metrics}
    card = cards[check["card"]["id"]]
    assert (card.value, card.as_of.isoformat(), card.source, card.unit) == (
        check["card"]["value"], check["card"]["as_of"], "NBR", "BDT trn")
    result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
    assert contradictions(result) == []
    assert result.state != "hold"
    assert family_view(result) == (sorted(check["family_reasons"]), sorted(check["family_unavailable"]))


def test_a_held_or_undated_nbr_figure_is_never_ready(tmp_path, monkeypatch):
    """Not fresh when it is not: the FY26 total in September and a night whose figure has no
    period both leave the publish degraded, never ready and never held."""
    for name in ("next-night-unchanged", "period-missing"):
        snap, rows = night_after(tmp_path, name)
        cards = {m.id: m for s in gathered_sections(monkeypatch, snap, rows) for m in s.metrics}
        result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
        assert result.state == "degraded", name
        assert any(r.split(":")[0] == "fiscal_nbr_collected_trn" for r in result.reasons) or \
            "fiscal_nbr_collected_trn" in result.unavailable, name


def test_the_producers_new_daily_skip_reasons_are_read_not_held_or_called_malformed(tmp_path, monkeypatch):
    """EconDelta now itemises 'period already recorded' and 'no source period' on the daily
    receipt. An ok daily write with those skips is a healthy receipt, not a contradiction."""
    for name in ("next-night-unchanged", "period-missing"):
        snap, rows = night_after(tmp_path, name)
        assert {s["category"] for s in snap.write_status["daily"]["skips"]} <= {
            "period already recorded", "no source period"}
        cards = {m.id: m for s in gathered_sections(monkeypatch, snap, rows) for m in s.metrics}
        result = assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)
        assert not [r for r in result.reasons if "persistence" in r], name
