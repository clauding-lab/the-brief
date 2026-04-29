from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_fiscal import render_section_fiscal
from brief.schema import Metric, NewsItem, SectionData


def _fiscal_section(*, with_metrics: bool = True, with_news: bool = True,
                    collected: float = 2.84) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="fiscal_nbr_collected_trn", label="NBR collected YTD", value=collected, unit="BDT trn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="fiscal_nbr_target_trn",    label="NBR full-year target", value=4.78, unit="BDT trn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="fiscal_adp_pct",           label="ADP utilisation",      value=42.5, unit="%",
                   as_of=date(2026, 3, 31), source="IMED", cadence="monthly"),
            Metric(id="fiscal_govt_borrow_trn",   label="Govt bank borrow YTD", value=0.96, unit="BDT trn",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="ADP utilisation lags target", url="https://example.com/fiscal1",
                     source="The Daily Star", published=datetime(2026, 4, 5, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="fiscal", title="Fiscal",
        kicker="FISCAL", tldr=f"NBR YTD: BDT {collected}trn",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[2.0, 2.2, 2.4, 2.55, 2.65, 2.75, collected],
    )


def test_section_fiscal_renders_with_full_metrics():
    html = render_section_fiscal(_fiscal_section())
    assert 'id="section-fiscal"' in html
    assert "§11" in html
    assert "FISCAL" in html
    assert "Fiscal" in html
    assert "2.84" in html
    assert "COLLECTED" in html
    assert "ADP" in html
    assert "BORROW" in html


def test_section_fiscal_renders_with_no_metrics():
    html = render_section_fiscal(_fiscal_section(with_metrics=False))
    assert 'id="section-fiscal"' in html
    assert "metric-card" not in html


def test_section_fiscal_renders_with_no_news():
    html = render_section_fiscal(_fiscal_section(with_news=False))
    assert 'id="section-fiscal"' in html
    assert '<ul class="sec-news">' not in html


def test_section_fiscal_no_threshold_badge_in_render():
    """fiscal has no deficit/pace metric in this builder; badge must never appear."""
    html_low  = render_section_fiscal(_fiscal_section(collected=0.1))
    html_high = render_section_fiscal(_fiscal_section(collected=99.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_fiscal_rejects_wrong_id():
    section = _fiscal_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_fiscal(section)
