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
    assert _section_n("exec") == "02"
    assert _section_n("bb") == "03"
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


# ---------------------------------------------------------------------------
# Section adapter — fills kicker/tldr when V4 builders leave them empty
# ---------------------------------------------------------------------------


def test_v5_apply_section_adapter_fills_empty_kicker():
    from brief.pipeline import _v5_apply_section_adapter

    s = _section("bb")  # _section() helper sets kicker=id_, but synthesize check needs empty
    s.kicker = ""  # simulate V4 builder default
    _v5_apply_section_adapter([s])

    assert s.kicker != ""
    assert s.kicker.isupper()  # kickers render uppercase, store uppercase


def test_v5_apply_section_adapter_preserves_existing_kicker():
    from brief.pipeline import _v5_apply_section_adapter

    s = _section("bb")
    s.kicker = "CUSTOM KICKER"
    _v5_apply_section_adapter([s])

    assert s.kicker == "CUSTOM KICKER"


def test_v5_apply_section_adapter_synthesises_tldr_from_primary_metric():
    from brief.pipeline import _v5_apply_section_adapter
    from brief.schema import Delta, Metric, SectionData

    s = SectionData(
        id="fx", title="FX & Reserves", kicker="FX", tldr="",
        metrics=[Metric(
            id="fx_usd_bdt", label="USD/BDT mid", value=122.7, unit="BDT",
            as_of=date(2026, 4, 21), source="BB", cadence="daily",
            delta=Delta(value=0.34, direction="up", window="dod"),
        )],
        news=[], freshness="fresh",
    )
    _v5_apply_section_adapter([s])

    # Synthesized tldr should mention the primary metric label and value
    assert "USD/BDT mid" in s.tldr
    assert "122.7" in s.tldr


def test_v5_apply_section_adapter_falls_back_when_no_metrics():
    """Sections without metrics (e.g. headlines) get a non-empty fallback tldr."""
    from brief.pipeline import _v5_apply_section_adapter
    from brief.schema import SectionData

    s = SectionData(
        id="headlines", title="Headlines", kicker="", tldr="",
        metrics=[], news=[], freshness="fresh",
    )
    _v5_apply_section_adapter([s])

    assert s.tldr != ""
    assert s.kicker != ""


def test_v5_apply_section_adapter_preserves_existing_tldr():
    from brief.pipeline import _v5_apply_section_adapter

    s = _section("bb")
    s.tldr = "Custom tldr"
    _v5_apply_section_adapter([s])

    assert s.tldr == "Custom tldr"


# ---------------------------------------------------------------------------
# call_reports observability — V5 calls must emit per-call cost/duration
# ---------------------------------------------------------------------------


def _fake_max_result(parsed=None, cost=0.05, duration=1.5, tokens=None):
    """Build a MaxCallResult-shaped object for mocking run_max returns."""
    from brief.claude.max_client import MaxCallResult
    return MaxCallResult(
        raw_text="{}",
        parsed=parsed,
        usage={"input_tokens": 100, "output_tokens": 50},
        total_cost_usd=cost,
        duration_s=duration,
        tokens=tokens or {"input": 100, "output": 50},
    )


def test_run_v5_editorial_call_2_populates_exec_signals():
    """Phase 2.2: Call 2 (exec_signals) fires between top_picks and todays_call.

    Valid signals payload mutates exec_section.exec_signals and bumps
    its freshness from 'pending' to 'fresh'. Emits an exec_signals
    entry in call_reports.
    """
    from brief.pipeline import run_v5_editorial

    sections = [
        _section("bb", "fresh"),
        _section("exec", "pending"),
    ]
    call_reports: list[dict] = []

    exec_payload = {
        "signals": [
            {"direction": "bull", "text": "BB reserves up 0.3bn WoW", "section_anchor": "bb"},
            {"direction": "warn", "text": "BB liquidity ratio at 8.5%", "section_anchor": "bb"},
        ],
        "traffic_status": "neu",
    }

    def fake_run_max(prompt=None, **kwargs):
        # Detect the exec_signals prompt by its unique copy
        if prompt and "Bangladesh signals" in prompt and "traffic_status" in prompt:
            return _fake_max_result(parsed=exec_payload)
        return _fake_max_result(parsed=None)

    with patch("brief.pipeline.run_max", side_effect=fake_run_max):
        run_v5_editorial(
            sections=sections,
            today=date(2026, 4, 21),
            headlines_curation_result={"selected": [], "rationale_bullet": ""},
            call_reports=call_reports,
        )

    names = [r["name"] for r in call_reports]
    assert "exec_signals" in names

    exec_section = next(s for s in sections if s.id == "exec")
    assert exec_section.exec_signals is not None
    assert len(exec_section.exec_signals) == 2
    assert exec_section.exec_signals[0].direction == "bull"
    assert exec_section.exec_signals[0].text == "BB reserves up 0.3bn WoW"
    # Successful Call 2 promotes the section from pending → fresh
    assert exec_section.freshness == "fresh"


def test_run_v5_editorial_call_2_invalid_payload_leaves_exec_pending():
    from brief.pipeline import run_v5_editorial

    sections = [_section("bb", "fresh"), _section("exec", "pending")]
    call_reports: list[dict] = []

    def fake_run_max(prompt=None, **kwargs):
        if prompt and "Bangladesh signals" in prompt:
            # malformed: signals isn't a list
            return _fake_max_result(parsed={"signals": "oops", "traffic_status": "neu"})
        return _fake_max_result(parsed=None)

    with patch("brief.pipeline.run_max", side_effect=fake_run_max):
        run_v5_editorial(
            sections=sections,
            today=date(2026, 4, 21),
            headlines_curation_result={"selected": [], "rationale_bullet": ""},
            call_reports=call_reports,
        )

    exec_section = next(s for s in sections if s.id == "exec")
    assert exec_section.exec_signals is None
    assert exec_section.freshness == "pending"  # unchanged
    # Call still recorded as invalid, not error
    rec = next(r for r in call_reports if r["name"] == "exec_signals")
    assert rec["status"] == "invalid"


def test_run_v5_editorial_records_call_report_per_run_max():
    """Each Claude call in run_v5_editorial appends an entry to call_reports.
    With 2 sections and parsed=None on every call, expected entries:
      - top_picks (1)
      - todays_call (1)
      - bankerread:<id> per section (2)
    No systemic_risk entries (test sections don't trigger risk rules).
    """
    from brief.pipeline import run_v5_editorial

    sections = [_section("s0"), _section("s1")]
    call_reports: list[dict] = []

    with patch("brief.pipeline.run_max", return_value=_fake_max_result(parsed=None)):
        run_v5_editorial(
            sections=sections,
            today=date(2026, 4, 21),
            headlines_curation_result={"selected": [], "rationale_bullet": ""},
            call_reports=call_reports,
        )

    names = [r["name"] for r in call_reports]
    assert "top_picks" in names
    assert "todays_call" in names
    assert "bankerread:s0" in names
    assert "bankerread:s1" in names
    assert len(call_reports) == 4

    # Each entry has the V4-compatible shape
    for r in call_reports:
        assert set(r.keys()) >= {"name", "status", "reason", "cost_usd", "duration_s", "tokens"}
        assert r["cost_usd"] == 0.05
        assert r["duration_s"] == 1.5


def test_run_v5_editorial_records_error_when_run_max_raises():
    from brief.pipeline import run_v5_editorial
    from brief.claude.max_client import MaxCallError

    sections = [_section("s0")]
    call_reports: list[dict] = []

    with patch("brief.pipeline.run_max", side_effect=MaxCallError("boom")):
        run_v5_editorial(
            sections=sections,
            today=date(2026, 4, 21),
            headlines_curation_result={"selected": [], "rationale_bullet": ""},
            call_reports=call_reports,
        )

    error_reports = [r for r in call_reports if r["status"] == "error"]
    assert len(error_reports) >= 3  # top_picks + todays_call + bankerread:s0
    assert all("boom" in (r["reason"] or "") for r in error_reports)


def test_run_v5_editorial_call_reports_optional():
    """Omitting call_reports (None) must not raise — back-compat for any caller
    that doesn't care about observability."""
    from brief.pipeline import run_v5_editorial

    with patch("brief.pipeline.run_max", return_value=_fake_max_result(parsed=None)):
        run_v5_editorial(
            sections=[_section("s0")],
            today=date(2026, 4, 21),
            headlines_curation_result={"selected": [], "rationale_bullet": ""},
        )  # no call_reports kwarg — must not raise


def test_run_v5_qa_gate_records_call_report():
    from brief.pipeline import run_v5_qa_gate

    sections = [_section("s0")]
    call_reports: list[dict] = []

    with patch("brief.pipeline.run_max", return_value=_fake_max_result(parsed=None)):
        run_v5_qa_gate(
            sections=sections,
            today=date(2026, 4, 21),
            todays_call=TodaysCall(text="word " * 80, generated_at=datetime.now(timezone.utc)),
            top_picks=_stub_top_picks(),
            rendered_html="<html></html>",
            call_reports=call_reports,
        )

    qa_reports = [r for r in call_reports if r["name"] == "editorial_qa"]
    assert len(qa_reports) == 1
    assert qa_reports[0]["cost_usd"] == 0.05


def test_render_index_html_v5_threads_call_reports_to_helpers():
    """render_index_html (V5 path) must forward call_reports to both
    run_v5_editorial and run_v5_qa_gate so per-call entries surface."""
    sections = [_stub_section(f"s{i}") for i in range(7)] + [_stub_section(f"g{i}") for i in range(7)]
    fake_qa = EditorialQAResult(status="pass", issues=[], shippable=True)
    fake_picks = _stub_top_picks()
    fake_call = TodaysCall(text="word " * 80, generated_at=datetime.now(timezone.utc))
    call_reports: list[dict] = []

    with patch.dict(os.environ, {"BRIEF_RENDERER": "v5"}, clear=False):
        with patch("brief.pipeline.run_v5_editorial",
                   return_value=(fake_picks, fake_call, {}, {})) as mock_editorial:
            with patch("brief.pipeline.run_v5_qa_gate", return_value=fake_qa) as mock_qa:
                render_index_html(
                    sections=sections,
                    today=date(2026, 4, 21),
                    today_label="Tue 21 Apr 2026",
                    live={"usd_bdt": 122.7, "dsex": 5232, "brent_usd": 95.1, "reserves_bn_usd": 34.12,
                          "generated_at": datetime.now(timezone.utc), "next_update_label": "18:00 CLOSE"},
                    run_meta={"vol": "II", "issue": 412, "sources_used": ["BB"], "render_duration_s": 0, "total_cost_usd": 0.0},
                    headlines_curation_result={"selected": [], "rationale_bullet": ""},
                    call_reports=call_reports,
                )

    assert mock_editorial.call_args.kwargs["call_reports"] is call_reports
    assert mock_qa.call_args.kwargs["call_reports"] is call_reports
