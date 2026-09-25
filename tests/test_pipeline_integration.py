import pytest

from brief.builders import ALL_BUILDER_IDS
from brief.pipeline import gather, PipelineConfig
from brief.schema import MapCoord, SectionData


@pytest.mark.integration
def test_gather_returns_11_sections(fixture_snapshot, today):
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)
    assert len(sections) == 11
    ids = [s.id for s in sections]
    # nbr dropped (no longer in spine). comm retired in v1.6.7 — Gold moved
    # into fx, LNG went away with the section. dam deleted in v1.6.8.
    assert ids == [
        "bb", "macro", "fx", "dse", "tbond", "iranwar",
        "headlines", "exec",
        "fiscal", "remit",
        "banking",
    ]
    for s in sections:
        assert isinstance(s, SectionData)
        assert s.freshness in ("fresh", "warning", "stale", "pending", "unavailable", "warming_up")


@pytest.mark.integration
def test_gather_enriches_metric_history_values(fixture_snapshot, today, monkeypatch):
    """When a history client is available, gather() populates Metric.history_values
    for every metric whose id appears in the batched response."""
    from unittest.mock import MagicMock
    from brief.history import MetricHistoryClient

    fake_client = MagicMock(spec=MetricHistoryClient)
    fake_client.get_history_window.return_value = {
        "bb_gross_reserves": [30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7],
        "fx_usd_bdt": [122.5, 122.6, 122.7],
    }
    fake_client.get_latest.return_value = None  # builders that fall back also work

    monkeypatch.setattr("brief.pipeline._build_history", lambda cfg: fake_client)

    cfg = PipelineConfig(today=today, enable_history=True, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)

    # Exactly one batched call was issued
    fake_client.get_history_window.assert_called_once()
    kwargs = fake_client.get_history_window.call_args.kwargs
    assert kwargs.get("days") == 14
    assert kwargs.get("today") == today

    # Reserves metric in the BB section gets enriched; metrics not in the
    # mock map keep history_values=None
    bb_section = next(s for s in sections if s.id == "bb")
    reserves_metric = next(m for m in bb_section.metrics if m.id == "bb_gross_reserves")
    assert reserves_metric.history_values == [30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7]

    # A metric NOT in the mock response stays at None
    policy_rate = next(m for m in bb_section.metrics if m.id == "bb_policy_rate")
    assert policy_rate.history_values is None


@pytest.mark.integration
def test_gather_no_history_no_enrichment_no_failure(fixture_snapshot, today):
    """When history is disabled, all metrics keep history_values=None and gather()
    completes without error."""
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)
    for s in sections:
        for m in s.metrics:
            assert m.history_values is None



def test_bank_borrowing_history_uses_bank_only_read_id_in_one_batch():
    from datetime import date
    from brief.pipeline import _enrich_metric_history
    from brief.schema import Metric

    class History:
        def __init__(self):
            self.calls = []

        def get_history_window(self, ids, **kwargs):
            self.calls.append(ids)
            rows = {"fiscal_govt_borrow_trn": [1.7, 1.8],
                    "fiscal_bank_borrow_trn": [-1.1, -1.2]}
            return {mid: rows[mid] for mid in ids if mid in rows}

    history = History()
    card = Metric(id="fiscal_govt_borrow_trn", label="Govt bank borrow YTD", value=-1.2,
                  unit="BDT trn", as_of=date(2026, 6, 30), source="BB", cadence="monthly")
    sections = [SectionData(id="fiscal", title="Fiscal", metrics=[card], freshness="stale")]
    _enrich_metric_history(sections, history, today=date(2026, 9, 25))
    assert card.history_values == [-1.1, -1.2]
    assert history.calls == [["fiscal_bank_borrow_trn"]]
