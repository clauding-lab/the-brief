"""R2 G2: the repaired Brief reading a snapshot from the PRE-REPAIR EconDelta producer.

This is the "new consumer + old producer" half of the release compatibility contract: it is
what production looks like if The Brief is deployed before EconDelta, or if EconDelta is
rolled back while the repaired Brief stays live.

Fixture provenance (tests/fixtures/compat/econdelta-latest-origin-main-6676887.json): the
byte-exact latest.json written by EconDelta origin/main commit 6676887 (#136, the code
production runs today) -- its real aggregate_latest.main(), run offline in the R2 G2 harness
(network refused, Supabase faked). Inputs: fix 2's realistic tree -- real WSEI (20 Sep 2026)
and MEI (July 2026) parser output, production Tier-1 / FSR / auction values captured 25 Sep
2026 14:49 BDT. SYNTHETIC parts: the scraped_at instants (inside the real 01:30-02:56 BDT
window) and the fixed 02:56 BDT 25 Sep clock. Its shape matches the production copy read on
28 Sep (no `observations`, no `write_status`, 'Z' capture time).

Policy pinned (R2 brief; fixes 3/10/4): an old-format snapshot never acquires a healthy
write status, never becomes a hold by itself, and a flat legacy scalar never borrows a
date -- a card with no dated evidence is unavailable, not invented.
"""
from __future__ import annotations

import hashlib
import json
import logging
import socket
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from brief import cli
from brief import pipeline as pipeline_module
from brief.econdelta import load_snapshot
from brief.history import HistoryRow
from brief.pipeline import PipelineConfig, gather
from brief.readiness import assess

LEGACY = Path(__file__).parent / "fixtures" / "compat" / "econdelta-latest-origin-main-6676887.json"
LEGACY_SHA256 = "bb467cf2d3bcdd0c9dcaaaf46a3b5fec17d0f107ed32bb3eb0a52cfa8b53aafb"
TODAY = date(2026, 9, 25)
RUN_AT = datetime(2026, 9, 25, 8, 0, tzinfo=timezone(timedelta(hours=6)))  # brief.timer, BDT
# The four daily quote cards and the flat legacy scalars they would print.
QUOTE_CARDS = {"fx_usd_bdt_mid": "usd_bdt_mid", "fx_gold_usd_oz": "gold_usd_oz",
               "iranwar_brent_spot": "brent_crude_usd_barrel", "iranwar_wti_spot": "wti_crude_usd_barrel"}


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """No live site, webhook or DSE scrape: a legacy snapshot must not send builders out."""
    def refuse(*args: object, **kwargs: object) -> None:
        raise OSError("test refused outbound network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for name in ("DISCORD_ALERT_WEBHOOK_URL", "DISCORD_PREVIEW_WEBHOOK_URL", "BRIEF_DRY_RUN"):
        monkeypatch.delenv(name, raising=False)
    from brief.builders import dse
    monkeypatch.setattr(dse, "scrape_breadth", lambda *a, **k: None)
    monkeypatch.setattr(dse, "scrape_sector_heat", lambda *a, **k: None)


class _ProductionShapedHistory:
    """Today's production metric_history for the quote ids: the same value, dated by the run
    day, with NO source_as_of (the R1 backup of production carries none on any row)."""

    def __init__(self, data: dict) -> None:
        self._rows = {mid: HistoryRow(mid, TODAY, data[mid], "EconDelta") for mid in QUOTE_CARDS.values()}

    def get_latest(self, metric_id: str, *, table: str = "metric_history") -> HistoryRow | None:
        return self._rows.get(metric_id) if table == "metric_history" else None

    def get_at_or_before(self, metric_id: str, as_of: date, *, table: str = "metric_history"):
        row = self.get_latest(metric_id, table=table)
        return row if row is not None and row.as_of <= as_of else None

    def get_history_window(self, metric_ids, **window: object) -> dict[str, list]:
        return {mid: [] for mid in metric_ids}  # no sparkline / chart history needed here


def _payload() -> dict:
    return json.loads(LEGACY.read_text())


def _config() -> PipelineConfig:
    return PipelineConfig(today=TODAY, enable_history=True, enable_headlines=False, econdelta_path=str(LEGACY))


def test_the_legacy_fixture_is_the_recorded_pre_repair_producer_output():
    # Any edit to the fixture must be a new, re-recorded producer run, not a hand change.
    assert hashlib.sha256(LEGACY.read_bytes()).hexdigest() == LEGACY_SHA256
    payload = _payload()
    assert "observations" not in payload and "write_status" not in payload
    assert set(payload["sources_status"]) == {"bb_forex", "dse_market", "commodity_prices"}


def test_a_pre_repair_snapshot_loads_without_invented_receipts_or_observations():
    snapshot = load_snapshot(LEGACY)
    assert snapshot.load_error is None
    assert snapshot.updated_at == datetime(2026, 9, 24, 20, 56, tzinfo=timezone.utc)
    assert snapshot.write_status is None
    assert snapshot.observations == {}
    assert snapshot.data == _payload()["data"]


def test_pre_repair_scalars_never_become_dated_quote_cards(monkeypatch):
    payload = _payload()
    monkeypatch.setattr(pipeline_module, "_build_history", lambda cfg: _ProductionShapedHistory(payload["data"]))
    sections = gather(_config())
    printed = {metric.id for section in sections for metric in section.metrics}
    # A flat scalar and a same-valued, undated history row are no observation date.
    assert printed.isdisjoint(QUOTE_CARDS)
    readiness = assess(sections.snapshot, persisted_rows=[m for s in sections for m in s.metrics], now=RUN_AT)
    assert set(QUOTE_CARDS.values()) <= set(readiness.unavailable)


def _publish(caplog):
    with caplog.at_level(logging.INFO), \
         patch("brief.alerts.send_discord_alert", return_value=True) as send, \
         patch("brief.cli.now_bdt", return_value=RUN_AT), \
         patch("brief.v6_publisher.fetch_same_day_briefs", return_value=[]), \
         patch("brief.v6_publisher.fetch_max_issue_no", return_value=235), \
         patch("brief.pipeline_v6.run_publish", return_value="brief-236") as run:
        rc = cli._run_v6_publish_unlocked(_config(), TODAY, dry_run=False, notify_enabled=False)
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Publication readiness:")]
    return rc, run, send, line


def test_a_pre_repair_snapshot_publishes_degraded_never_ready_and_never_held(caplog, monkeypatch):
    monkeypatch.setattr(pipeline_module, "_build_history", lambda cfg: None)
    rc, run, send, line = _publish(caplog)
    assert line.startswith("Publication readiness: degraded; ")
    # Absent receipts stay unconfirmed: never a fictitious healthy write.
    assert "daily persistence unconfirmed (no receipt)" in line
    assert "monthly persistence unconfirmed (no receipt)" in line
    # A pre-fix-5 producer reports no upstream CPI/M2 poll: unknown, never a polled job.
    assert "CPI upstream source-poll liveness not reported by EconDelta" in line
    assert "M2 upstream source-poll liveness not reported by EconDelta" in line
    # A current, readable capture: no snapshot alert, and the publish goes ahead.
    assert not send.called
    assert run.call_count == 1 and rc == 0
