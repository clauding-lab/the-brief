"""V5 pipeline integration tests with mocked run_max."""
import os
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from brief.pipeline import (
    _placement_for,
    _section_n,
    _strip_css_and_script,
    _top_picks_fallback,
    render_index_html,
    renderer_mode,
)
from brief.schema import (
    BankerReadInsight,
    EditorialQAResult,
    GridEntry,
    MapPoint,
    Metric,
    QAIssue,
    SectionData,
    TodaysCall,
    TopPicks,
)


def _section(id_: str, freshness: str = "fresh", with_metric: bool = True) -> SectionData:
    metrics = []
    if with_metric:
        metrics.append(Metric(
            id=f"{id_}_x", label="x", value=1.0, unit="x",
            as_of=date(2026, 4, 21), source="x", cadence="daily",
        ))
    return SectionData(id=id_, title=id_, kicker=id_, tldr="", metrics=metrics, news=[], freshness=freshness)


def test_section_n_mapping():
    assert _section_n("bb") == "02"
    assert _section_n("iranwar") == "08"
    assert _section_n("unknown") == "??"


def test_top_picks_fallback_emits_seven_plotted_seven_grid():
    sections = [_section(f"s{i}") for i in range(14)]
    picks = _top_picks_fallback(sections)
    assert len(picks.plotted) == 7
    assert len(picks.grid) == 7
    assert {p.id for p in picks.plotted} | {g.id for g in picks.grid} == {f"s{i}" for i in range(14)}


def test_strip_css_and_script_removes_blocks():
    html = '<div>keep</div><style>body{color:red}</style><script>x</script><p>also keep</p>'
    s = _strip_css_and_script(html)
    assert "keep" in s
    assert "also keep" in s
    assert "color:red" not in s
    assert "<script" not in s


def test_placement_for():
    picks = TopPicks(
        plotted=[MapPoint(id=f"p{i}", x=1, y=1, r=10, kind="fresh") for i in range(7)],
        grid=[GridEntry(id=f"g{i}", tldr="x") for i in range(7)],
        front_of_book_id="p0",
    )
    assert _placement_for("p0", picks) == {"plotted": True, "front_of_book": True, "grid": False}
    assert _placement_for("g3", picks) == {"plotted": False, "front_of_book": False, "grid": True}
    assert _placement_for("ghost", picks) == {"plotted": False, "front_of_book": False, "grid": False}


def test_renderer_mode_default_v4():
    with patch.dict(os.environ, {}, clear=True):
        assert renderer_mode() == "v4"


def test_renderer_mode_v5_explicit():
    with patch.dict(os.environ, {"BRIEF_RENDERER": "v5"}, clear=True):
        assert renderer_mode() == "v5"


def test_renderer_mode_uppercase_normalized():
    with patch.dict(os.environ, {"BRIEF_RENDERER": "V5"}, clear=True):
        assert renderer_mode() == "v5"


# ---------------------------------------------------------------------------
# render_index_html dispatch tests
# ---------------------------------------------------------------------------


def _stub_section(id_: str) -> SectionData:
    return SectionData(
        id=id_, title=f"{id_} title", kicker=id_, tldr="",
        metrics=[], news=[], freshness="warming_up",
    )


def _stub_top_picks() -> TopPicks:
    plotted = [MapPoint(id=f"s{i}", x=1, y=1, r=10, kind="fresh") for i in range(7)]
    grid = [GridEntry(id=f"g{i}", tldr=f"tldr {i}") for i in range(7)]
    return TopPicks(plotted=plotted, grid=grid, front_of_book_id="s0")


def test_render_index_html_v5_returns_meta_with_qa():
    """V5 dispatch path: returns (html, meta) where meta has renderer_mode and qa."""
    sections = [_stub_section(f"s{i}") for i in range(7)] + [_stub_section(f"g{i}") for i in range(7)]
    fake_qa = EditorialQAResult(status="pass", issues=[], shippable=True)
    fake_picks = _stub_top_picks()
    fake_call = TodaysCall(text="word " * 80, generated_at=datetime.now(timezone.utc))

    with patch.dict(os.environ, {"BRIEF_RENDERER": "v5"}, clear=False):
        with patch("brief.pipeline.run_v5_editorial", return_value=(fake_picks, fake_call, {}, {})) as mock_v5:
            with patch("brief.pipeline.run_v5_qa_gate", return_value=fake_qa):
                html, meta = render_index_html(
                    sections=sections,
                    today=date(2026, 4, 21),
                    today_label="Tue 21 Apr 2026",
                    live={"usd_bdt": 122.7, "dsex": 5232, "brent_usd": 95.1, "reserves_bn_usd": 34.12,
                          "generated_at": datetime.now(timezone.utc), "next_update_label": "18:00 CLOSE"},
                    run_meta={"vol": "II", "issue": 412, "sources_used": ["BB"], "render_duration_s": 0, "total_cost_usd": 0.0},
                    headlines_curation_result={"selected": [], "rationale_bullet": ""},
                )

    assert meta["renderer_mode"] == "v5"
    assert meta["qa"]["shippable"] is True
    assert "<!DOCTYPE html>" in html
    mock_v5.assert_called_once()


def test_render_index_html_v5_qa_block_returns_unshippable():
    """V5 dispatch path: qa.shippable=False is reflected in meta; caller decides what to do."""
    sections = [_stub_section(f"s{i}") for i in range(7)] + [_stub_section(f"g{i}") for i in range(7)]
    fake_qa = EditorialQAResult(
        status="block",
        issues=[QAIssue(section_id="bb", severity="block", message="missing pull_quote")],
        shippable=False,
    )
    fake_picks = _stub_top_picks()
    fake_call = TodaysCall(text="word " * 80, generated_at=datetime.now(timezone.utc))

    with patch.dict(os.environ, {"BRIEF_RENDERER": "v5"}, clear=False):
        with patch("brief.pipeline.run_v5_editorial", return_value=(fake_picks, fake_call, {}, {})):
            with patch("brief.pipeline.run_v5_qa_gate", return_value=fake_qa):
                html, meta = render_index_html(
                    sections=sections,
                    today=date(2026, 4, 21),
                    today_label="Tue 21 Apr 2026",
                    live={"usd_bdt": 122.7, "dsex": 5232, "brent_usd": 95.1, "reserves_bn_usd": 34.12,
                          "generated_at": datetime.now(timezone.utc), "next_update_label": "18:00 CLOSE"},
                    run_meta={"vol": "II", "issue": 412, "sources_used": ["BB"], "render_duration_s": 0, "total_cost_usd": 0.0},
                    headlines_curation_result={"selected": [], "rationale_bullet": ""},
                )

    assert meta["renderer_mode"] == "v5"
    assert meta["qa"]["shippable"] is False
    assert len(meta["qa"]["issues"]) == 1


# ---------------------------------------------------------------------------
# pipeline.run() dispatches to V5 path when BRIEF_RENDERER=v5
# ---------------------------------------------------------------------------


def test_pipeline_run_dispatches_to_v5_when_env_set():
    """When BRIEF_RENDERER=v5, pipeline.run() must invoke render_index_html (V5 path)
    and return a RunResult with the V5 HTML, NOT call render_v4."""
    from brief.pipeline import PipelineConfig, run

    sections = [_stub_section(f"s{i}") for i in range(14)]

    def fake_render_index_html(**kwargs):
        return ("<!DOCTYPE html><html><body>V5 OUTPUT</body></html>",
                {"renderer_mode": "v5", "qa": {"shippable": True, "status": "pass", "issues": []}})

    with patch.dict(os.environ, {"BRIEF_RENDERER": "v5"}, clear=False):
        with patch("brief.pipeline.gather", return_value=sections):
            with patch("brief.pipeline._run_v5_headlines_curation",
                       return_value=({"selected": [], "rationale_bullet": ""}, [])):
                with patch("brief.pipeline.render_index_html",
                           side_effect=fake_render_index_html) as mock_render:
                    with patch("brief.pipeline.render_v4") as mock_v4:
                        cfg = PipelineConfig(today=date(2026, 4, 26))
                        rr = run(cfg)

    assert "V5 OUTPUT" in rr.html
    assert rr.sections == sections
    mock_render.assert_called_once()
    mock_v4.assert_not_called()


def test_pipeline_run_default_v4_path_unchanged():
    """When BRIEF_RENDERER is unset (default v4), pipeline.run() must NOT invoke
    render_index_html. V4 path stays intact."""
    from brief.pipeline import PipelineConfig, run

    with patch.dict(os.environ, {}, clear=True):
        with patch("brief.pipeline.render_index_html") as mock_render:
            with patch("brief.pipeline.run_pipeline") as mock_pipeline:
                # Stop run() early — we only need to verify v5 path NOT taken
                mock_pipeline.side_effect = RuntimeError("v4 path was reached as expected")
                cfg = PipelineConfig(today=date(2026, 4, 26))
                try:
                    run(cfg)
                except RuntimeError as e:
                    assert "v4 path was reached" in str(e)

    mock_render.assert_not_called()
