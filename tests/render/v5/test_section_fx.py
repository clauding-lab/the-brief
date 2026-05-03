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
            Metric(id="fx_eur_bdt",      label="EUR/BDT",      value=132.10, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_gross_reserves", label="Gross Reserves", value=35.04, unit="bn USD",
                   as_of=date(2026, 4, 15), source="BB", cadence="weekly"),
            Metric(id="fx_monthly_exports", label="Monthly Exports", value=3.48, unit="bn USD",
                   as_of=date(2026, 3, 31), source="EPB", cadence="monthly"),
            Metric(id="fx_trade_gap", label="Trade Gap", value=-3.0, unit="bn USD",
                   as_of=date(2026, 3, 31), source="EPB · BB", cadence="monthly"),
            Metric(id="fx_monthly_remittance", label="Monthly Remittance", value=3.755, unit="bn USD",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
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
    assert "122.50" in html  # hero USD/BDT mid value
    # Post-2026-05-03: external-balance row replaces buy/sell/EUR/GBP variants
    assert "USD/BDT" in html
    assert "Gross Reserves" in html
    assert "35.04" in html
    assert "Monthly Exports" in html
    assert "3.48" in html
    assert "Trade Gap" in html
    assert "Monthly Remittance" in html
    assert "3.75" in html or "3.755" in html  # remittance — fmt_num 2dp truncates 3.755 to 3.75


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
