from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_nbr import render_section_nbr
from brief.schema import Metric, NewsItem, SectionData


def _nbr_section(*, with_metrics: bool = True, with_news: bool = True, vat_value: float = 142.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="nbr_vat_bn",     label="VAT",        value=vat_value, unit="BDT bn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="nbr_it_bn",      label="Income Tax", value=98.7, unit="BDT bn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="nbr_customs_bn", label="Customs",    value=64.2, unit="BDT bn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="VAT collection up 8% YoY", url="https://example.com/nbr1",
                     source="Bonik Barta", published=datetime(2026, 4, 5, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="nbr", title="NBR Revenue",
        kicker="TAX & CUSTOMS", tldr=f"VAT: BDT {vat_value}bn",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[120, 125, 130, 135, 138, 140, vat_value],
    )


def test_section_nbr_renders_with_full_metrics():
    html = render_section_nbr(_nbr_section())
    assert 'id="section-nbr"' in html
    assert "§12" in html
    assert "TAX" in html
    assert "NBR Revenue" in html
    assert "142.50" in html
    assert "VAT" in html
    assert "IT" in html
    assert "CUSTOMS" in html


def test_section_nbr_renders_with_no_metrics():
    html = render_section_nbr(_nbr_section(with_metrics=False))
    assert 'id="section-nbr"' in html
    assert "metric-card" not in html


def test_section_nbr_renders_with_no_news():
    html = render_section_nbr(_nbr_section(with_news=False))
    assert 'id="section-nbr"' in html
    assert '<ul class="sec-news">' not in html


def test_section_nbr_no_threshold_badge_in_render():
    """NBR has no FYTD/target metric; badge must never appear regardless of values."""
    html_low  = render_section_nbr(_nbr_section(vat_value=10.0))
    html_high = render_section_nbr(_nbr_section(vat_value=999.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_nbr_rejects_wrong_id():
    section = _nbr_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_nbr(section)
