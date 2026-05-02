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
