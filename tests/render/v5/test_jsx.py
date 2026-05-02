import re
from datetime import date

import pytest

from brief.render.v5 import _jsx
from brief.schema import (
    BankerReadInsight,
    Metric,
    NewsItem,
    SystemicRisk,
)
from datetime import datetime, timezone


def test_kind_dot_emits_class():
    html = _jsx.kind_dot("event")
    assert 'class="dot dot-event"' in html


def test_kind_dot_rejects_unknown():
    with pytest.raises(ValueError):
        _jsx.kind_dot("explosion")


def test_freshness_pill_fresh_no_visible_text():
    html = _jsx.freshness_pill("fresh")
    assert "FRESH" not in html  # fresh is implied; no pill text


def test_freshness_pill_stale_visible_text():
    html = _jsx.freshness_pill("stale")
    assert "STALE" in html
    assert 'class="freshness-pill freshness-stale"' in html


def test_cadence_pill_uppercases():
    html = _jsx.cadence_pill_v5("daily")
    assert ">DAILY<" in html


def test_pull_quote_card_renders_text():
    html = _jsx.pull_quote_card("Risk premium, not scarcity.")
    assert "Risk premium, not scarcity." in html
    assert 'class="pull-quote-card"' in html


def test_metric_hero_card_with_status_badge():
    metric = Metric(
        id="bb_npl",
        label="NPL Ratio",
        value=35.73,
        unit="%",
        as_of=date(2026, 4, 19),
        source="BB",
        cadence="quarterly",
    )
    html = _jsx.metric_hero_card(metric, badge="HISTORIC HIGH", supporting="World's highest")
    assert "35.73" in html
    assert "HISTORIC HIGH" in html
    assert "World's highest" in html


def test_metric_hero_card_renders_aging_chip_when_warning():
    # monthly cadence, 40 days old → warning band → AGING chip
    metric = Metric(
        id="cpi_food",
        label="CPI Food",
        value=10.4,
        unit="%",
        as_of=date(2026, 3, 12),
        source="BBS",
        cadence="monthly",
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    assert 'class="metric-aging-chip"' in html
    assert "AGING" in html


def test_metric_hero_card_no_aging_chip_when_fresh():
    metric = Metric(
        id="cpi_food",
        label="CPI Food",
        value=10.4,
        unit="%",
        as_of=date(2026, 4, 15),  # 6 days, well within fresh
        source="BBS",
        cadence="monthly",
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    assert "metric-aging-chip" not in html


def test_metric_hero_card_renders_source_meta():
    metric = Metric(
        id="cpi_food",
        label="CPI Food",
        value=10.4,
        unit="%",
        as_of=date(2026, 4, 15),
        source="BBS",
        cadence="monthly",
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    # source/date footer is the anchor for the AGING chip per V1 mockup
    assert 'class="metric-meta"' in html
    assert "BBS" in html


def test_metric_hero_card_no_meta_when_value_none():
    # Don't render meta line when there's nothing to show
    metric = Metric(
        id="cpi_food",
        label="CPI Food",
        value=None,
        unit="%",
        as_of=date(2026, 4, 15),
        source="BBS",
        cadence="monthly",
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    assert "metric-meta" not in html


def test_metric_hero_card_renders_sparkline_when_enough_history():
    metric = Metric(
        id="cpi", label="CPI", value=10.0, unit="%",
        as_of=date(2026, 4, 15), source="BBS", cadence="monthly",
        history_values=[8.0, 8.5, 9.0, 9.5, 10.0, 10.2, 10.0],
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    assert "<svg" in html
    assert 'class="sparkline"' in html
    assert 'class="metric-sparkline' in html


def test_metric_hero_card_no_sparkline_below_minimum_points():
    metric = Metric(
        id="cpi", label="CPI", value=10.0, unit="%",
        as_of=date(2026, 4, 15), source="BBS", cadence="monthly",
        history_values=[8.0, 9.0, 10.0],  # only 3
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    assert "metric-sparkline" not in html


def test_metric_hero_card_no_sparkline_when_history_none():
    metric = Metric(
        id="cpi", label="CPI", value=10.0, unit="%",
        as_of=date(2026, 4, 15), source="BBS", cadence="monthly",
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    assert "metric-sparkline" not in html


def test_metric_hero_card_hero_flag_uses_oxblood_stroke():
    metric = Metric(
        id="cpi", label="CPI", value=10.0, unit="%",
        as_of=date(2026, 4, 15), source="BBS", cadence="monthly", hero=True,
        history_values=[8.0, 8.5, 9.0, 9.5, 10.0, 10.2, 10.0],
    )
    html = _jsx.metric_hero_card(metric, today=date(2026, 4, 21))
    # hero cards get the oxblood (#6b1f27) stroke; non-hero gets default
    assert 'stroke="#6b1f27"' in html
    assert "metric-sparkline-hero" in html


# ── line_chart_svg (Phase 2.3) ──────────────────────────────────────────────

def test_line_chart_svg_renders_path_with_labels():
    series = [11.85, 12.05, 12.20, 12.40, 12.60, 12.92]
    labels = ["3M", "6M", "1Y", "2Y", "5Y", "10Y"]
    html = _jsx.line_chart_svg(series, x_labels=labels, y_min=11.5, y_max=13.2,
                               w=520, h=220)
    assert "<svg" in html
    assert 'viewBox="0 0 520 220"' in html
    # Each label rendered as text
    for lab in labels:
        assert f">{lab}<" in html
    # Path opens with M then has 5 L commands (6 points)
    assert html.count(' L') == 5


def test_line_chart_svg_with_comparison_renders_dashed_line():
    series = [11.85, 12.05, 12.20]
    prev = [11.76, 11.96, 12.12]
    html = _jsx.line_chart_svg(
        series, x_labels=["3M", "6M", "1Y"],
        y_min=11.5, y_max=13.0,
        comparison_series=prev,
    )
    # Comparison uses stroke-dasharray for the dashed line
    assert "stroke-dasharray" in html
    # Two <path> elements: comparison + main
    assert html.count("<path") == 2


def test_line_chart_svg_returns_empty_on_too_few_points():
    assert _jsx.line_chart_svg([12.0], x_labels=["3M"], y_min=10, y_max=14) == ""
    assert _jsx.line_chart_svg([], x_labels=[], y_min=10, y_max=14) == ""


def test_line_chart_svg_skips_none_values():
    series = [11.85, None, 12.20, None, 12.60, 12.92]
    labels = ["3M", "6M", "1Y", "2Y", "5Y", "10Y"]
    html = _jsx.line_chart_svg(series, x_labels=labels, y_min=11.5, y_max=13.2)
    # Gaps split the path: M at i=0, M at i=2, M at i=4, L at i=5
    # Path is "M…M…M…L…" — 1 L, 3 Ms in the d attribute
    assert html.count(' L') == 1
    # 4 non-None values → 4 dot markers
    assert html.count("<circle") == 4
    # All 6 labels still rendered (hide nothing on the x-axis)
    for lab in labels:
        assert f">{lab}<" in html


def test_line_chart_svg_auto_min_max_when_omitted():
    series = [11.0, 12.0, 13.0]
    html = _jsx.line_chart_svg(series, x_labels=["a", "b", "c"])
    # Falls back to data min/max — chart still renders
    assert "<svg" in html
    assert "<path" in html


def test_source_badge_known_code_uses_css_class():
    html = _jsx.source_badge("REU")
    assert 'class="source-badge source-badge-reu"' in html
    assert "REU" in html


def test_source_badge_full_name_resolves_to_code():
    html = _jsx.source_badge("The Daily Star")
    assert "source-badge-ds" in html
    # The visible label is the short code, not the long name
    assert ">DS<" in html


def test_source_badge_unknown_falls_back_to_default():
    html = _jsx.source_badge("Some Obscure Outlet")
    assert "source-badge-default" in html
    assert "Some Obscure Outlet" in html


def test_news_bullet_renders_source_as_lozenge():
    item = NewsItem(
        title="NPL ratio at 35.73%",
        url="https://example.com/x",
        source="TBS",
        published=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    html = _jsx.news_bullet(item, summary="...")
    assert "source-badge-tbs" in html
    assert "TBS" in html


def test_news_bullet_renders_source_and_date():
    item = NewsItem(
        title="NPL ratio at 35.73%",
        url="https://example.com/x",
        source="TBS",
        published=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    html = _jsx.news_bullet(item, summary="The NPL ratio surged to 35.73% as of September 2025...")
    assert "NPL ratio at 35.73%" in html
    assert "TBS" in html
    assert "19 Apr 2026" in html  # date format


def test_bankerread_panel_v5_full_renders_all_four():
    br = BankerReadInsight(
        variant="full",
        meaning="m" * 80,
        action="a" * 80,
        trigger="t" * 80,
        focus="f" * 80,
        pull_quote="quotable",
        generated_at=datetime.now(timezone.utc),
    )
    html = _jsx.bankerread_panel_v5(br, anchor="bb")
    assert "§A" in html
    assert "§B" in html
    assert "§C" in html
    assert "§D" in html


def test_bankerread_panel_v5_stale_renders_meaning_only():
    br = BankerReadInsight(
        variant="stale_micro",
        meaning="single paragraph " * 8,
        pull_quote="quotable",
        generated_at=datetime.now(timezone.utc),
    )
    html = _jsx.bankerread_panel_v5(br, anchor="bb")
    assert "§A" in html
    assert "§B" not in html  # action skipped on stale
    assert "§C" not in html
    assert "§D" not in html


def test_systemic_risk_callout_renders_warning_class():
    risk = SystemicRisk(
        headline="NPL world-high",
        body="Body text " * 10,
        level="warning",
        rule_id="banking_npl_above_30",
    )
    html = _jsx.systemic_risk_callout(risk)
    assert "systemic-risk" in html
    assert "warning" in html
    assert "NPL world-high" in html


def test_bankerread_panel_v5_v4_legacy_raises():
    br = BankerReadInsight(
        variant="v4_legacy",
        sentences=["s1", "s2", "s3", "s4"],
        generated_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValueError):
        _jsx.bankerread_panel_v5(br, anchor="bb")


def test_no_raw_html_in_news_summary_attack():
    """Defense: news summary must be HTML-escaped to prevent injection."""
    item = NewsItem(
        title="<script>alert(1)</script>",
        url="https://x.test/",
        source="X",
        published=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    html = _jsx.news_bullet(item, summary="<img onerror=x>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img onerror" not in html
    assert "&lt;img" in html
