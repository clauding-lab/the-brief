import pytest

from brief.pipeline import gather, PipelineConfig
from brief.schema import SectionData


@pytest.mark.integration
def test_gather_returns_14_sections(fixture_snapshot, today):
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)
    assert len(sections) == 14
    ids = [s.id for s in sections]
    assert ids == [
        "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
        "headlines", "exec",
        "comm", "banking", "dam", "fiscal", "nbr",
    ]
    for s in sections:
        assert isinstance(s, SectionData)
        assert s.freshness in ("fresh", "warning", "stale", "pending", "unavailable")


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


from pathlib import Path

FIXTURE_SHELL = Path(__file__).parent.parent / "fixtures" / "sample_the_brief.html"


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
        ]
        result = run(cfg, shell_path=FIXTURE_SHELL, snapshot_override=fixture_snapshot)
    assert "OLD_BB_BODY" not in result.html
    assert "SectionRMG" not in result.html
    assert result.html.startswith("<!DOCTYPE html>")
