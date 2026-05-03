from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_comm import render_section_comm
from brief.schema import Metric, NewsItem, SectionData


def _comm_section(*, with_metrics: bool = True, with_news: bool = True,
                  gold_oz: float = 2415.50) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="comm_gold_usd_oz",  label="Gold",     value=gold_oz, unit="USD/oz",
                   as_of=date(2026, 4, 28), source="EconDelta", cadence="daily"),
            Metric(id="comm_gold_22k_bdt", label="Gold 22K", value=147500.0, unit="BDT/bhori",
                   as_of=date(2026, 4, 28), source="BAJUS", cadence="daily"),
            Metric(id="comm_lng_jkm",      label="LNG JKM",  value=12.4, unit="USD/MMBtu",
                   as_of=date(2026, 4, 25), source="History", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Gold pulls back from $2,420 high", url="https://example.com/comm1",
                     source="Reuters", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="comm", title="Commodities",
        kicker="COMMODITIES", tldr=f"Gold ${gold_oz}/oz",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[2380, 2390, 2400, 2410, 2415, 2420, gold_oz],
    )


def test_section_comm_renders_with_full_metrics():
    html = render_section_comm(_comm_section())
    assert 'id="section-comm"' in html
    assert "§10" in html
    assert "COMMODITIES" in html
    assert "Commodities" in html
    assert "2415.50" in html or "2,415.50" in html
    assert "GOLD" in html
    assert "LNG" in html


def test_section_comm_renders_with_no_metrics():
    html = render_section_comm(_comm_section(with_metrics=False))
    assert 'id="section-comm"' in html
    assert "metric-card" not in html


def test_section_comm_renders_with_no_news():
    html = render_section_comm(_comm_section(with_news=False))
    assert 'id="section-comm"' in html
    assert '<ul class="sec-news">' not in html


def test_section_comm_no_threshold_badge_in_render():
    """comm has no brent metric in this builder; badge must never appear."""
    html_low  = render_section_comm(_comm_section(gold_oz=1500.0))
    html_high = render_section_comm(_comm_section(gold_oz=4500.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_comm_rejects_wrong_id():
    section = _comm_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_comm(section)
