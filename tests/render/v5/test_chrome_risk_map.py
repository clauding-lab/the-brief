from datetime import datetime, timezone

from brief.render.v5.chrome.risk_map import render_risk_map
from brief.schema import GridEntry, MapPoint, TopPicks


def _section_lookup():
    """Minimal section catalog used by the risk map for labels."""
    return {
        "bb":      {"kicker": "Policy & rates", "n": "02"},
        "macro":   {"kicker": "Inflation",      "n": "03"},
        "fx":      {"kicker": "FX & external",  "n": "04"},
        "remit":   {"kicker": "Remittance",     "n": "05"},
        "dse":     {"kicker": "Equities · DSE", "n": "06"},
        "tbond":   {"kicker": "T-Bill & T-Bond","n": "07"},
        "iranwar": {"kicker": "Iran · Oil",     "n": "08"},
    }


def test_risk_map_renders_seven_bubbles_with_legend():
    plotted = [
        MapPoint(id="bb",      x=1.2, y=6.0, r=24, kind="anchor"),
        MapPoint(id="macro",   x=2.2, y=7.8, r=32, kind="slow"),
        MapPoint(id="fx",      x=3.4, y=6.3, r=28, kind="slow"),
        MapPoint(id="remit",   x=6.0, y=7.0, r=30, kind="fresh"),
        MapPoint(id="dse",     x=6.5, y=4.8, r=26, kind="fresh"),
        MapPoint(id="tbond",   x=5.0, y=5.4, r=24, kind="fresh"),
        MapPoint(id="iranwar", x=9.4, y=9.1, r=38, kind="event"),
    ]
    grid = [GridEntry(id=f"g{i}", tldr=f"tldr {i}") for i in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="iranwar")

    html = render_risk_map(picks=picks, sections=_section_lookup(), today_label="Tue 21 Apr 2026")

    # Seven circles
    assert html.count('<circle ') == 7
    # Quadrant labels
    for label in ("SLOW · STRUCTURAL", "ACTIVE · MATERIAL", "DORMANT", "NOISE"):
        assert label in html
    # Legend
    for kind in ("EVENT", "FRESH PRINT", "SLOW · STRUCTURAL", "ANCHOR"):
        assert kind in html
    # Read-first arrow points to front-of-book section
    assert "read first" in html.lower()


def test_risk_map_rejects_empty_plotted_after_headlines_filter():
    """Renderer must reject a TopPicks where filtering headlines leaves nothing.

    The strict 'exactly 7' rule was relaxed to tolerate the headlines filter
    (which can drop one bubble if Claude mistakenly placed headlines on the map).
    But an entirely empty plot is still an error worth surfacing.
    """
    plotted = [MapPoint(id="headlines", x=5, y=5, r=20, kind="event")]
    grid = [GridEntry(id=f"g{i}", tldr="x") for i in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="headlines")

    import pytest
    with pytest.raises(ValueError, match="nothing to plot"):
        render_risk_map(picks=picks, sections=_section_lookup(), today_label="x")
