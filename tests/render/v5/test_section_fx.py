from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_fx import render_section_fx
from brief.schema import Metric, NewsItem, SectionData


def _fx_section(*, with_metrics: bool = True, with_news: bool = True, hero_value: float = 122.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="fx_usd_bdt_mid",  label="USD/BDT mid",  value=hero_value, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_usd_bdt_buy",  label="USD/BDT buy",  value=hero_value - 0.5, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_usd_bdt_sell", label="USD/BDT sell", value=hero_value + 0.5, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_eur_bdt",      label="EUR/BDT",      value=132.10, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_gbp_bdt",      label="GBP/BDT",      value=154.75, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Taka steady against dollar mid-week", url="https://example.com/fx1",
                     source="Daily Star", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="fx", title="Foreign Exchange",
        kicker="FX & RESERVES", tldr="USD/BDT 122.50; eur 132.10",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[121.8, 122.0, 122.1, 122.2, 122.3, 122.4, 122.5],
    )


def test_section_fx_renders_with_full_metrics():
    html = render_section_fx(_fx_section())
    assert 'id="section-fx"' in html
    assert "§05" in html
    assert "FX" in html  # kicker
    assert "Foreign Exchange" in html
    assert "122.50" in html  # hero value
    assert "USD/BDT" in html
    assert "EUR/BDT" in html
    assert "GBP/BDT" in html


def test_section_fx_renders_with_no_metrics():
    section = _fx_section(with_metrics=False)
    html = render_section_fx(section)
    assert 'id="section-fx"' in html
    # No orphan empty metric grid wrappers
    assert "metric-card" not in html


def test_section_fx_renders_with_no_news():
    section = _fx_section(with_news=False)
    html = render_section_fx(section)
    assert 'id="section-fx"' in html
    assert '<ul class="sec-news">' not in html


def test_section_fx_threshold_badge_above_124():
    html = render_section_fx(_fx_section(hero_value=125.5))
    assert "WATCH" in html


def test_section_fx_rejects_wrong_id():
    section = _fx_section().model_copy(update={"id": "macro"})
    with pytest.raises(ValueError):
        render_section_fx(section)
