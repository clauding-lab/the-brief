from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_dse import render_section_dse
from brief.schema import Metric, NewsItem, SectionData


def _dse_section(*, with_metrics: bool = True, with_news: bool = True,
                 advancing: float = 220, declining: float = 110) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="dse_dsex_close",      label="DSEX close",  value=5481.42, unit="index",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_dsex_change_pct", label="DSEX %Δ",     value=0.45, unit="%",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_ds30",            label="DS30",        value=2007.31, unit="index",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_dses",            label="DSES",        value=1196.55, unit="index",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_turnover_crore",  label="Turnover",    value=620.5, unit="crore BDT",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_advancing",       label="Advancing",   value=advancing, unit="stocks",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_declining",       label="Declining",   value=declining, unit="stocks",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="DSEX edges up on banking gains", url="https://example.com/dse1",
                     source="The Daily Star", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="dse", title="DSE Markets",
        kicker="EQUITIES", tldr="DSEX 5,481; turnover 620cr",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[5410, 5430, 5450, 5460, 5470, 5475, 5481],
    )


def test_section_dse_renders_with_full_metrics():
    html = render_section_dse(_dse_section())
    assert 'id="section-dse"' in html
    assert "§06" in html
    assert "EQUITIES" in html
    assert "DSE Markets" in html
    assert "5481.42" in html or "5,481.42" in html
    assert "DSEX" in html
    assert "DS30" in html
    assert "TURNOVER" in html


def test_section_dse_renders_with_no_metrics():
    html = render_section_dse(_dse_section(with_metrics=False))
    assert 'id="section-dse"' in html
    assert "metric-card" not in html


def test_section_dse_renders_with_no_news():
    html = render_section_dse(_dse_section(with_news=False))
    assert 'id="section-dse"' in html
    assert '<ul class="sec-news">' not in html


def test_section_dse_threshold_badge_breadth_below_30():
    # advancing=50, declining=200 → breadth = 50/(50+200) = 20% → WATCH
    html = render_section_dse(_dse_section(advancing=50, declining=200))
    assert "WATCH" in html


def test_section_dse_rejects_wrong_id():
    section = _dse_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_dse(section)
