import pytest

from brief.builders import ALL_BUILDER_IDS
from brief.pipeline import gather, PipelineConfig
from brief.schema import MapCoord, SectionData


@pytest.mark.integration
def test_gather_returns_9_sections(fixture_snapshot, today):
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)
    assert len(sections) == 9
    ids = [s.id for s in sections]
    # Post-2026-05-03: remit/comm/dam/fiscal/nbr excluded
    assert ids == [
        "bb", "macro", "fx", "dse", "tbond", "iranwar",
        "headlines", "exec",
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


from unittest.mock import patch

from brief.claude.max_client import MaxCallResult
from brief.pipeline import run_pipeline


def _fake_curation(urls):
    return MaxCallResult(
        raw_text="{}",
        parsed={"selected": [{"url": u, "domain": "fx", "weight": "med"} for u in urls[:2]],
                "rationale_bullet": "test"},
        usage={}, total_cost_usd=0,
    )


def _fake_signals():
    return MaxCallResult(
        raw_text="{}",
        parsed={"signals": [{"direction": "bull", "text": "reserves up",
                             "section_anchor": "bb"}],
                "traffic_status": "neu"},
        usage={}, total_cost_usd=0,
    )


def _fake_insights():
    return MaxCallResult(
        raw_text="{}",
        parsed={"insights": {"fx": ["one", "two", "three", "four"]}},
        usage={}, total_cost_usd=0,
    )


def _fake_insights_stale():
    return MaxCallResult(
        raw_text="{}",
        parsed={"insights": {"bb": ["No fresh data; reserves dated to early March."]}},
        usage={}, total_cost_usd=0,
    )


def test_run_pipeline_injects_claude_outputs(fixture_snapshot, today):
    from brief.pipeline import PipelineConfig

    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)

    call_count = {"n": 0}
    responses = [
        _fake_curation([]),
        _fake_signals(),
        _fake_insights(),         # bankerread_full for fresh+warning sections
        _fake_insights_stale(),   # bankerread_stale for stale sections (bb)
    ]

    def _stub(**kwargs):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r

    with patch("brief.pipeline.run_max", side_effect=_stub):
        result = run_pipeline(cfg, snapshot_override=fixture_snapshot)

    assert call_count["n"] == 4
    exec_section = next(s for s in result.sections if s.id == "exec")
    assert exec_section.exec_signals is not None
    assert len(exec_section.exec_signals) >= 1

    # bb is stale in the canonical fixture (reserves_date 51 days old) so it
    # should receive the freeform (stale_micro) variant from the bankerread_stale call.
    bb = next(s for s in result.sections if s.id == "bb")
    assert bb.bankerread is not None
    assert bb.bankerread.kind == "freeform"

    # fx is fresh in the fixture and should receive the structured (full) variant.
    fx = next(s for s in result.sections if s.id == "fx")
    assert fx.bankerread is not None
    assert fx.bankerread.kind == "structured"


_RISK_MAP_IDS = ["bb", "macro", "fx", "remit", "dse", "tbond", "iranwar", "comm", "banking", "dam", "fiscal", "nbr"]


def _fake_risk_map():
    sections = [
        {
            "section_id": sid,
            "x": 5.0,
            "y": 5.0,
            "r": 30,
            "type": "slow",
            "hero_metric_id": None,
        }
        for sid in _RISK_MAP_IDS
    ]
    read_order = [s["section_id"] for s in sections]
    return MaxCallResult(
        raw_text="{}",
        parsed={"sections": sections, "read_order": read_order},
        usage={}, total_cost_usd=0,
    )


_FAKE_CALL_TEXT = (
    # V5 validator requires 60-100 words; this is ~80 words.
    "Bangladesh foreign-exchange reserves climbed for a third straight week "
    "as remittance inflows held firm, narrowing the current-account gap and "
    "giving the central bank room to hold its policy rate steady into the next "
    "quarter without triggering further taka depreciation against the dollar "
    "while food inflation held above ten percent adding to imported pressure "
    "from oil channels. Hedge the fixed-rate corporate book before next print."
)


def _fake_todays_call():
    return MaxCallResult(
        raw_text="{}",
        parsed={"text": _FAKE_CALL_TEXT, "byline": "Desk Editor · The Brief"},
        usage={}, total_cost_usd=0,
    )


def test_run_returns_html(fixture_snapshot, today):
    from brief.pipeline import PipelineConfig, run
    cfg = PipelineConfig(
        today=today, enable_history=False, enable_headlines=False,
    )
    with patch("brief.pipeline.run_max") as mx:
        mx.side_effect = [
            _fake_curation([]),
            _fake_signals(),
            _fake_insights(),
            _fake_insights_stale(),
            _fake_risk_map(),
            _fake_todays_call(),
        ]
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)
    assert "OLD_BB_BODY" not in result.html
    assert "SectionRMG" not in result.html
    assert result.html.startswith("<!DOCTYPE html>")
    # V4-specific content checks
    assert "risk-map" in result.html
    assert "masthead" in result.html
    assert "section-bb" in result.html


def test_run_populates_risk_map_and_todays_call(fixture_snapshot, today):
    """RunResult carries map_coords, read_order, todays_call (from fake)."""
    from brief.pipeline import PipelineConfig, run

    cfg = PipelineConfig(
        today=today, enable_history=False, enable_headlines=False,
    )
    with patch("brief.pipeline.run_max") as mx:
        mx.side_effect = [
            _fake_curation([]),
            _fake_signals(),
            _fake_insights(),
            _fake_insights_stale(),
            _fake_risk_map(),
            _fake_todays_call(),
        ]
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)

    assert len(result.map_coords) == 7
    assert all(isinstance(mc, MapCoord) for mc in result.map_coords)
    assert len(result.read_order) == 7
    assert set(result.read_order) == {"bb", "macro", "fx", "dse", "tbond", "iranwar", "banking"}
    assert result.todays_call is not None
    assert result.todays_call.text == _FAKE_CALL_TEXT
    assert result.todays_call.byline == "Desk Editor · The Brief"


def test_run_falls_back_when_risk_map_fails(fixture_snapshot, today):
    """When risk_map_layout Claude response is invalid, fallback produces 12 coords (exec + headlines excluded)."""
    from brief.pipeline import PipelineConfig, run

    cfg = PipelineConfig(
        today=today, enable_history=False, enable_headlines=False,
    )
    # Risk map returns empty sections list -- validator will reject (count mismatch)
    _fake_risk_map_invalid = MaxCallResult(
        raw_text="{}",
        parsed={"sections": [], "read_order": []},
        usage={}, total_cost_usd=0,
    )

    with patch("brief.pipeline.run_max") as mx:
        mx.side_effect = [
            _fake_curation([]),
            _fake_signals(),
            _fake_insights(),
            _fake_insights_stale(),
            _fake_risk_map_invalid,
            _fake_todays_call(),
        ]
        result = run(cfg, shell_path=None, snapshot_override=fixture_snapshot)

    # Deterministic fallback must produce 12 coords (exec + headlines excluded)
    assert len(result.map_coords) == 7
    # Claude's todays_call still succeeded (valid response after fallback risk_map)
    assert result.todays_call.text == _FAKE_CALL_TEXT
