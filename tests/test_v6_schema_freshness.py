"""Verify new V6 freshness fields parse cleanly with sensible defaults."""
from datetime import date

from brief.v6_schema import BriefV6, CoverMetricV6, MetricV6, NewsItemV6


def test_metric_accepts_held_from():
    m = MetricV6(label="NPL Ratio", value="35.73%", held_from="2026-04-18", next_print="Q1 2026")
    assert m.held_from == date(2026, 4, 18)
    assert m.next_print == "Q1 2026"


def test_metric_held_from_optional():
    m = MetricV6(label="Brent", value="$113.95")
    assert m.held_from is None
    assert m.next_print is None


def test_news_accepts_held_from():
    n = NewsItemV6(headline="X happened", held_from="2026-05-01")
    assert n.held_from == date(2026, 5, 1)


def test_news_held_from_optional():
    n = NewsItemV6(headline="Y happened")
    assert n.held_from is None


def test_brief_accepts_lens_and_frame():
    b = BriefV6(issue_no=1, volume=1, brief_date="2026-05-05", lens="banking", frame="credit-cycle")
    assert b.lens == "banking"
    assert b.frame == "credit-cycle"


def test_brief_lens_frame_optional():
    b = BriefV6(issue_no=1, volume=1, brief_date="2026-05-05")
    assert b.lens is None
    assert b.frame is None


def test_cover_metric_accepts_held_from():
    c = CoverMetricV6(label="NPL", value="35.73%", held_from="2026-04-18", next_print="Q1 2026")
    assert c.held_from == date(2026, 4, 18)
    assert c.next_print == "Q1 2026"
