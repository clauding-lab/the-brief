"""Stopped upstream CPI/M2 jobs degrade the Brief even when the aggregate succeeded (R2 fix 5).

EconDelta publishes its E6 upstream source-poll liveness for the CPI and M2 families in
latest.json's sources_status (shared contract: upstream_liveness_contract). Its CPI/M2
monthly legs reread EconDelta's own database, which says nothing about whether the
Bangladesh Bank jobs still poll. So a snapshot whose writes and rereads all succeeded
must still read degraded, naming CPI and M2 and why, never ready.

Limits: the entries are the contract's producer output (EconDelta's
tests/test_upstream_liveness.py pins that its real aggregate run writes exactly these);
no real upstream source is polled here.
"""
from datetime import date, datetime, timezone

import pytest

from brief.econdelta import EconDeltaSnapshot
from brief.readiness import assess
from brief.schema import Metric
from tests.test_producer_consumer_contract import (
    BRIEF_RUN,
    aggregate_run,
    gathered_cards,
)
from tests.upstream_liveness import CONTRACT
from tests.upstream_liveness import POLLED_UPSTREAM as POLLED
from tests.upstream_liveness import STOPPED_UPSTREAM as STOPPED

NOW = datetime(2026, 9, 25, 3, tzinfo=timezone.utc)
OBS = {"metric_id": "quote", "value": 80, "unit": "USD/barrel", "as_of": "2026-09-23",
       "captured_at": "2026-09-25T02:00:00+00:00", "source": "official",
       "evidence": "dated row", "quality": "verified", "date_basis": "observation"}
ROW = Metric(id="quote", label="Quote", value=80, unit="USD/barrel", source="official",
             as_of=date(2026, 9, 23), cadence="daily")
RECEIPTS = {stage: {"status": "ok", "attempted_at": NOW.isoformat()} for stage in ("daily", "monthly")}


def clean_snapshot(upstream: dict) -> EconDeltaSnapshot:
    """Every write confirmed, every reading current: only the upstream entries vary."""
    return EconDeltaSnapshot(NOW, dict(upstream), {"quote": 80}, {"quote": OBS}, RECEIPTS)


def test_a_clean_run_is_ready_only_while_the_cpi_m2_jobs_are_polled():
    assert assess(clean_snapshot(POLLED), persisted_rows=[ROW], now=NOW).state == "ready"


def unreported(label: str) -> str:
    return (f"{label} upstream source-poll liveness not reported by EconDelta "
            "(no entry in sources_status)")


def test_a_snapshot_without_cpi_m2_liveness_entries_is_never_read_as_polled():
    """Absent liveness is unknown, not healthy (like an absent write receipt): a pre-fix-5
    producer during deploy skew, or a producer that drops the keys, must not let a clean
    aggregate hide stopped CPI/M2 jobs."""
    result = assess(clean_snapshot({}), persisted_rows=[ROW], now=NOW)
    assert (result.state, result.reasons) == ("degraded", (
        f"source cpi_upstream_poll: missing ({unreported('CPI')})",
        f"source m2_upstream_poll: missing ({unreported('M2')})",
    ))


@pytest.mark.parametrize("dropped", sorted(CONTRACT["families"]))
def test_dropping_one_family_entry_degrades_naming_only_that_family(dropped):
    """Every family the shared contract lists is required; the one still reported as
    polled adds nothing."""
    label = CONTRACT["families"][dropped]["label"]
    kept = {key: entry for key, entry in POLLED.items() if key != dropped}
    result = assess(clean_snapshot(kept), persisted_rows=[ROW], now=NOW)
    assert (result.state, result.reasons) == (
        "degraded", (f"source {dropped}: missing ({unreported(label)})",))


def test_stopped_cpi_m2_jobs_degrade_a_clean_run_naming_each_family_and_why():
    result = assess(clean_snapshot(STOPPED), persisted_rows=[ROW], now=NOW)
    assert result.state == "degraded"
    assert result.reasons == (
        ("source cpi_upstream_poll: missing (CPI upstream source-poll liveness not established: "
         "database reread only, not an upstream source poll (cpi_12m_avg_monthly, "
         "cpi_p2p_food_monthly, cpi_p2p_nonfood_monthly))"),
        ("source m2_upstream_poll: missing (M2 upstream source-poll liveness not established: "
         "database reread only, not an upstream source poll (m2_growth_yoy_monthly))"),
    )


def test_the_realistic_aggregate_run_through_every_builder_names_stopped_cpi_m2_jobs(
        tmp_path, monkeypatch):
    """The contract's real aggregate run, read by every real builder: never held, and the
    CPI/M2 liveness reasons appear only when the upstream jobs have stopped."""
    snap, rows = aggregate_run(tmp_path)
    cards = gathered_cards(monkeypatch, snap, rows)

    def upstream_reasons(entries: dict) -> list[str]:
        with_entries = EconDeltaSnapshot(snap.updated_at, {**snap.sources_status, **entries}, snap.data,
                                         snap.observations, snap.write_status)
        result = assess(with_entries, persisted_rows=cards, now=BRIEF_RUN)
        assert result.state == "degraded"  # held monthly readings are reported either way
        return [r for r in result.reasons if "_upstream_poll" in r]

    assert upstream_reasons(POLLED) == []
    stopped = upstream_reasons(STOPPED)
    assert [r.split(":")[0] for r in stopped] == ["source cpi_upstream_poll", "source m2_upstream_poll"]
    assert all("database reread only, not an upstream source poll" in r for r in stopped)
