from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_dam import render_section_dam
from brief.schema import Metric, NewsItem, SectionData


def _dam_section(*, with_metrics: bool = True, with_news: bool = True,
                 rice: float = 58.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="dam_rice_coarse", label="Rice (coarse)", value=rice, unit="BDT/kg",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
            Metric(id="dam_flour",       label="Wheat flour",   value=52.0, unit="BDT/kg",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
            Metric(id="dam_lentil",      label="Red lentil",    value=125.0, unit="BDT/kg",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
            Metric(id="dam_oil",         label="Soybean oil",   value=178.0, unit="BDT/L",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Rice prices firm in Dhaka markets", url="https://example.com/dam1",
                     source="The Daily Star", published=datetime(2026, 4, 25, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="dam", title="DAM Food Prices",
        kicker="FOOD PRICES", tldr=f"Rice coarse: BDT {rice}/kg",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[55.0, 56.0, 57.0, 57.5, 58.0, 58.2, rice],
    )


def test_section_dam_renders_with_full_metrics():
    html = render_section_dam(_dam_section())
    assert 'id="section-dam"' in html
    assert "§14" in html
    assert "FOOD" in html
    assert "DAM Food Prices" in html
    assert "58.50" in html
    assert "RICE" in html
    assert "FLOUR" in html
    assert "LENTIL" in html


def test_section_dam_renders_with_no_metrics():
    html = render_section_dam(_dam_section(with_metrics=False))
    assert 'id="section-dam"' in html
    assert "metric-card" not in html


def test_section_dam_renders_with_no_news():
    html = render_section_dam(_dam_section(with_news=False))
    assert 'id="section-dam"' in html
    assert '<ul class="sec-news">' not in html


def test_section_dam_no_threshold_badge_in_render():
    """dam V4 builder doesn't populate Metric.delta; badge must never appear."""
    html_low  = render_section_dam(_dam_section(rice=10.0))
    html_high = render_section_dam(_dam_section(rice=999.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_dam_rejects_wrong_id():
    section = _dam_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_dam(section)
