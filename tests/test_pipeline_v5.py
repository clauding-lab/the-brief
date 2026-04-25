"""V5 pipeline integration tests with mocked run_max."""
import os
from datetime import date, datetime, timezone
from unittest.mock import patch

from brief.pipeline import (
    _placement_for,
    _section_n,
    _strip_css_and_script,
    _top_picks_fallback,
    renderer_mode,
)
from brief.schema import GridEntry, MapPoint, Metric, SectionData, TopPicks


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
