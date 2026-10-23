"""R2 fix R1B round 2: the NBR release blocker the round-1 release order leaves open.

Owner decisions (d)+(l) remove the reviewed capture-date restamps of the NBR family, 140 rows
per id dated 2026-05-02..2026-09-24. The round-1 release rule applies them before the new
EconDelta producer's first history write, so that night leaves exactly one properly dated row
per id (the contract's real 25 Sep "first-night" run: FY26, 2026-06-30). But the deployed
producer keeps re-saving the standing total with each later capture day until the new producer
replaces it (EconDelta landmine 47), and the reviewed list stops at 2026-09-24. Any such row
left in metric_history is newer than the period row, so the NBR card reads it and the Brief
HOLDs on every fire. Only a further owner-reviewed exclusion of those post-window restamps,
bound to their values and keeping the producer's period row, clears it.
"""
from __future__ import annotations

from datetime import date

import pytest

from brief.history import HistoryRow
from brief.readiness import assess
from tests.test_nbr_fytd_card import FAMILY, night_after
from tests.test_producer_consumer_contract import BRIEF_RUN, contradictions, gathered_sections

CARD_ID = "fiscal_nbr_collected_trn"
PERIOD_ROW_DATE = date(2026, 6, 30)  # the new producer's first-night row (FY26, source-stated)
LAST_REVIEWED_RESTAMP = date(2026, 9, 24)  # decisions (d)+(l) end here
# The first capture day after the reviewed window; with the contract's run day (25 Sep) it is the
# only such day not in the future. It stands for every capture day up to the release night.
POST_WINDOW_CAPTURE_DAY = date(2026, 9, 25)
# SYNTHETIC rows: production after the 25 Sep backup is unknown here. Their shape and values copy
# the backup's last reviewed restamp run (2026-09-06..09-24: source EconDelta, parent and alias
# 415,473.0 crore, child 4.15 trn), which the deployed producer re-saves every capture day.
DEPLOYED_PRODUCER_RESTAMP = {"tax_revenue": 415473.0, "nbr_fytd_collected_cr": 415473.0,
                             "fiscal_nbr_collected_trn": 4.15}
HOLD_REASON = f"{CARD_ID}: builder and accepted observation disagree"


def post_window_restamps() -> list[HistoryRow]:
    return [HistoryRow(mid, POST_WINDOW_CAPTURE_DAY, value, "EconDelta")
            for mid, value in DEPLOYED_PRODUCER_RESTAMP.items()]


def is_post_window_restamp(row: HistoryRow) -> bool:
    """Exactly one reviewed restamp key per id, bound to its reviewed value (the H1 strictness)."""
    return (row.metric_id in DEPLOYED_PRODUCER_RESTAMP and row.as_of == POST_WINDOW_CAPTURE_DAY
            and row.value == DEPLOYED_PRODUCER_RESTAMP[row.metric_id])


def publish(monkeypatch, snap, rows):
    cards = {m.id: m for s in gathered_sections(monkeypatch, snap, rows) for m in s.metrics}
    return cards[CARD_ID], assess(snap, persisted_rows=cards.values(), now=BRIEF_RUN)


def test_the_synthetic_restamps_sit_after_the_reviewed_window_and_after_the_period_row():
    assert POST_WINDOW_CAPTURE_DAY > LAST_REVIEWED_RESTAMP > PERIOD_ROW_DATE
    assert POST_WINDOW_CAPTURE_DAY <= BRIEF_RUN.date()
    assert set(DEPLOYED_PRODUCER_RESTAMP) == set(FAMILY)


@pytest.mark.parametrize("night", ["first-night", "next-night-unchanged"])
def test_r1_applied_before_the_first_night_still_holds_while_a_post_window_restamp_remains(
        tmp_path, monkeypatch, night):
    """Following the round-1 order exactly: the period row is the only reviewed-era row left, yet
    one later restamp makes the card print a capture date, and the publish HOLDs. The next night
    the producer re-sends nothing ("period already recorded"), so the HOLD never ends by itself."""
    snap, rows = night_after(tmp_path, night)
    card, result = publish(monkeypatch, snap, [*rows, *post_window_restamps()])
    assert (card.value, card.as_of) == (4.15, POST_WINDOW_CAPTURE_DAY)
    assert result.state == "hold"
    assert contradictions(result) == [HOLD_REASON]


def test_without_a_post_window_restamp_the_same_night_is_never_held(tmp_path, monkeypatch):
    """The control: the round-1 order on history with no later restamp publishes the period row."""
    snap, rows = night_after(tmp_path, "first-night")
    card, result = publish(monkeypatch, snap, rows)
    assert (card.value, card.as_of) == (4.15, PERIOD_ROW_DATE)
    assert contradictions(result) == []
    assert result.state == "degraded"


def test_excluding_only_the_value_bound_post_window_restamps_keeps_the_period_row_and_clears_the_hold(
        tmp_path, monkeypatch):
    snap, rows = night_after(tmp_path, "first-night")
    history = [row for row in [*rows, *post_window_restamps()] if not is_post_window_restamp(row)]
    assert sorted((r.metric_id, r.as_of) for r in history if r.metric_id in FAMILY) == sorted(
        (mid, PERIOD_ROW_DATE) for mid in FAMILY)
    card, result = publish(monkeypatch, snap, history)
    assert (card.value, card.as_of) == (4.15, PERIOD_ROW_DATE)
    assert contradictions(result) == []
    assert result.state == "degraded"


def test_an_exclusion_that_also_deletes_the_producers_period_row_still_holds(tmp_path, monkeypatch):
    """The wrong remedy ("the reviewed keys plus everything recaptured"): the card loses its only
    properly dated figure and no longer matches the accepted observation, so the publish HOLDs."""
    snap, rows = night_after(tmp_path, "first-night")
    history = [row for row in [*rows, *post_window_restamps()] if row.metric_id not in FAMILY]
    card, result = publish(monkeypatch, snap, history)
    assert card.value is None
    assert result.state == "hold"
    assert contradictions(result) == [HOLD_REASON]
