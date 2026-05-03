from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_iranwar import render_section_iranwar
from brief.schema import Metric, NewsItem, SectionData


@dataclass(frozen=True)
class _OilEvent:
    """Test mirror of brief.builders.iranwar.OilEvent."""
    date: date
    label: str
    hot: bool


def _iranwar_section(*, with_metrics: bool = True, with_news: bool = True,
                     with_events: bool = True, brent: float = 84.20) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="iranwar_brent_spot", label="Brent spot", value=brent, unit="USD/bbl",
                   as_of=date(2026, 4, 28), source="EconDelta", cadence="daily"),
            Metric(id="iranwar_wti_spot",   label="WTI spot",   value=brent - 4.0, unit="USD/bbl",
                   as_of=date(2026, 4, 28), source="EconDelta", cadence="daily"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Brent hovers in mid-80s as Iran tensions ease", url="https://example.com/iw1",
                     source="Reuters", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    section = SectionData(
        id="iranwar", title="Iran War & Oil",
        kicker="GLOBAL OIL", tldr=f"Brent ${brent}/bbl",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[83.0, 83.5, 83.8, 84.0, 84.1, 84.15, brent],
    )
    if with_events:
        section.extras["oil_events"] = [
            _OilEvent(date=date(2026, 4, 21), label="Hormuz tanker", hot=True),
            _OilEvent(date=date(2026, 4, 11), label="OPEC+ hold", hot=False),
            _OilEvent(date=date(2026, 4, 2),  label="IAEA report", hot=False),
        ]
    return section


def test_section_iranwar_renders_with_full_data():
    html = render_section_iranwar(_iranwar_section())
    assert 'id="section-iranwar"' in html
    assert "§08" in html
    assert "GLOBAL OIL" in html
    assert "Iran War" in html
    assert "84.20" in html
    assert "BRENT" in html
    assert "WTI" in html
    assert "EVENTS" in html
    assert "Hormuz tanker" in html
    assert "oil-events" in html


def test_section_iranwar_renders_with_no_metrics():
    html = render_section_iranwar(_iranwar_section(with_metrics=False))
    assert 'id="section-iranwar"' in html
    assert "metric-card" not in html


def test_section_iranwar_renders_with_no_events():
    html = render_section_iranwar(_iranwar_section(with_events=False))
    assert 'id="section-iranwar"' in html
    assert "oil-events" not in html
    assert "Hormuz tanker" not in html


def test_section_iranwar_threshold_badge_brent_above_100():
    html = render_section_iranwar(_iranwar_section(brent=105.0))
    assert "CRITICAL" in html


def test_section_iranwar_rejects_wrong_id():
    section = _iranwar_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_iranwar(section)
