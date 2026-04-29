from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_tbond import render_section_tbond
from brief.schema import Metric, NewsItem, SectionData


def _tbond_section(*, with_metrics: bool = True, with_news: bool = True,
                   bond_10y: float = 11.42) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="tbond_tbill_91d",  label="91d T-Bill cut-off",  value=9.85, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_tbill_182d", label="182d T-Bill cut-off", value=10.20, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_tbill_364d", label="364d T-Bill cut-off", value=10.55, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_bond_5y",    label="5y Govt Bond",        value=11.10, unit="%",
                   as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
            Metric(id="tbond_bond_10y",   label="10y Govt Bond",       value=bond_10y, unit="%",
                   as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="10y bond yield holds above 11%", url="https://example.com/tbond1",
                     source="The Financial Express", published=datetime(2026, 4, 25, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="tbond", title="T-Bonds & T-Bills",
        kicker="TREASURY", tldr=f"10y: {bond_10y}%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[11.0, 11.1, 11.2, 11.25, 11.3, 11.38, bond_10y],
    )


def test_section_tbond_renders_with_full_metrics():
    html = render_section_tbond(_tbond_section())
    assert 'id="section-tbond"' in html
    assert "§07" in html
    assert "TREASURY" in html
    assert "T-Bonds" in html
    assert "11.42" in html
    assert "10Y" in html
    assert "5Y" in html
    assert "91D" in html


def test_section_tbond_renders_with_no_metrics():
    html = render_section_tbond(_tbond_section(with_metrics=False))
    assert 'id="section-tbond"' in html
    assert "metric-card" not in html


def test_section_tbond_renders_with_no_news():
    html = render_section_tbond(_tbond_section(with_news=False))
    assert 'id="section-tbond"' in html
    assert '<ul class="sec-news">' not in html


def test_section_tbond_threshold_badge_above_12():
    html = render_section_tbond(_tbond_section(bond_10y=12.5))
    assert "WATCH" in html


def test_section_tbond_rejects_wrong_id():
    section = _tbond_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_tbond(section)
