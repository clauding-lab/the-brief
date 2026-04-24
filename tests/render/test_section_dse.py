from datetime import date

from brief.render.templates.section_dse import render
from brief.schema import Metric, SectionData


def _section():
    base_kwargs = dict(unit="x", as_of=date(2026, 4, 20), source="DSE", cadence="daily")
    return SectionData(
        id="dse", title="DSE Markets",
        metrics=[
            Metric(id="dse_dsex_close", label="DSEX", value=5232.49, **base_kwargs),
            Metric(id="dse_advancing", label="Advancing", value=120, **base_kwargs),
            Metric(id="dse_declining", label="Declining", value=207, **base_kwargs),
        ],
        freshness="fresh",
    )


def test_dse_render_shows_breadth():
    out = render(_section())
    assert out.startswith("function SectionDSE()")
    assert "5,232.49" in out
    assert "Advancing" in out
    assert "Declining" in out
    assert 'id="section-dse"' in out
