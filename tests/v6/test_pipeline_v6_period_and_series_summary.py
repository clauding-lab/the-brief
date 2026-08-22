"""P2 fact-checker (2026-08-22 audit #204) — items 2 & 3:
  - every metric in `_to_v6_raw`'s output carries a deterministic `period`
  - a pre-editor `series_summary` digest is fetched and stamped per section,
    without disturbing the post-editor `_stamp_chart_series` full-series stamp
"""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

from brief.pipeline_v6 import (
    _build_editor_input,
    _fetch_series_summaries,
    _to_v6_raw,
    summarize_series_points,
)
from brief.schema import Metric, SectionData
from brief.v6_schema import SeriesPointV6


def _metric(**kw) -> Metric:
    base = dict(id="m1", label="M1", value=1.0, unit="%", as_of=date(2026, 7, 31),
                source="BB", cadence="monthly")
    base.update(kw)
    return Metric(**base)


# ─── item 2: `period` on every raw metric ──────────────────────────────────


def test_to_v6_raw_stamps_monthly_period():
    sections = [SectionData(id="macro", title="Macro", freshness="fresh",
                             metrics=[_metric(cadence="monthly", as_of=date(2026, 7, 31))])]
    raw = _to_v6_raw(sections, today=date(2026, 8, 22))
    assert raw[0]["metrics"][0]["period"] == "Jul 2026"


def test_to_v6_raw_stamps_quarterly_period():
    sections = [SectionData(id="banking", title="Banking", freshness="fresh",
                             metrics=[_metric(cadence="quarterly", as_of=date(2026, 6, 30))])]
    raw = _to_v6_raw(sections, today=date(2026, 8, 22))
    assert raw[0]["metrics"][0]["period"] == "Q2 2026"


def test_to_v6_raw_stamps_daily_period():
    sections = [SectionData(id="dse", title="DSE Markets", freshness="fresh",
                             metrics=[_metric(cadence="daily", as_of=date(2026, 8, 22))])]
    raw = _to_v6_raw(sections, today=date(2026, 8, 22))
    assert raw[0]["metrics"][0]["period"] == "22 Aug 2026"


def test_to_v6_raw_stamps_period_even_on_a_fresh_metric():
    """Unlike `vintage` (null when fresh), `period` is ALWAYS present."""
    sections = [SectionData(id="bb", title="Bangladesh Bank", freshness="fresh",
                             metrics=[_metric(cadence="event", as_of=date(2026, 8, 22))])]
    raw = _to_v6_raw(sections, today=date(2026, 8, 22))
    m = raw[0]["metrics"][0]
    assert m["vintage"] is None
    assert m["period"] == "22 Aug 2026"


# ─── item 3: series_summary ─────────────────────────────────────────────────


def test_summarize_series_points_reduces_to_digest():
    points = [
        SeriesPointV6(key="dsex", ts="2026-06-01", value=5000.0),
        SeriesPointV6(key="dsex", ts="2026-07-01", value=5200.0),
        SeriesPointV6(key="dsex", ts="2026-08-01", value=5100.0),
    ]
    out = summarize_series_points(points)
    assert out == {
        "dsex": {
            "n": 3, "first_ts": "2026-06-01", "first_value": 5000.0,
            "last_ts": "2026-08-01", "last_value": 5100.0,
            "min": 5000.0, "max": 5200.0,
        }
    }


def test_summarize_series_points_sorts_before_reducing():
    """Callers don't need to pre-sort — out-of-order input still reduces correctly."""
    points = [
        SeriesPointV6(key="brent", ts="2026-08-01", value=90.0),
        SeriesPointV6(key="brent", ts="2026-06-01", value=80.0),
        SeriesPointV6(key="brent", ts="2026-07-01", value=85.0),
    ]
    out = summarize_series_points(points)
    assert out["brent"]["first_ts"] == "2026-06-01"
    assert out["brent"]["first_value"] == 80.0
    assert out["brent"]["last_ts"] == "2026-08-01"
    assert out["brent"]["last_value"] == 90.0


def test_summarize_series_points_groups_multiple_keys_separately():
    points = [
        SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-06-01", value=4202.69),
        SeriesPointV6(key="imports_usd_mn_monthly", ts="2026-03-01", value=5826.2),
    ]
    out = summarize_series_points(points)
    assert set(out) == {"exports_usd_mn_monthly", "imports_usd_mn_monthly"}
    assert out["exports_usd_mn_monthly"]["n"] == 1


def test_fetch_series_summaries_degrades_gracefully_on_a_single_fetcher_failure():
    """One fetcher raising must not take down the other slugs' summaries."""
    with patch("brief.pipeline_v6.chart_series_fetcher.fetch_macro_cpi_series",
               side_effect=RuntimeError("boom")), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_remit_monthly",
               return_value={"remittance_usd_mn_monthly": [
                   SeriesPointV6(key="remittance_usd_mn_monthly", ts="2026-07-31", value=2858.68),
               ]}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_reserves_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_yield_ladder_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_fx_balance_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_fiscal_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_dsex", return_value=([], [])), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_brent", return_value=[]):
        out = _fetch_series_summaries(
            today=date(2026, 8, 22), http=object(),
            supabase_url="https://test.supabase.co", service_key="key",
        )
    assert "macro" not in out  # the failing fetcher's slug is simply absent
    assert out["remit"]["remittance_usd_mn_monthly"]["last_value"] == 2858.68


def test_build_editor_input_stamps_empty_series_summary_by_default():
    sections = [SectionData(id="macro", title="Macro", freshness="fresh", metrics=[])]
    with patch("brief.pipeline_v6.fetch_max_issue_no", return_value=1):
        editor_input, _lens = _build_editor_input(
            sections, date(2026, 8, 22), [],
            previous_brief=None, previous_lens=None, recent_news=[], metric_definitions=[],
        )
    assert editor_input["sections_raw"][0]["series_summary"] == {}


def test_build_editor_input_stamps_provided_series_summary_per_slug():
    sections = [SectionData(id="macro", title="Macro", freshness="fresh", metrics=[])]
    digest = {"macro": {"cpi_12m_avg_monthly": {"n": 24, "first_ts": "2024-08-01",
                                                 "first_value": 6.0, "last_ts": "2026-07-31",
                                                 "last_value": 5.2, "min": 4.8, "max": 6.5}}}
    with patch("brief.pipeline_v6.fetch_max_issue_no", return_value=1):
        editor_input, _lens = _build_editor_input(
            sections, date(2026, 8, 22), [],
            previous_brief=None, previous_lens=None, recent_news=[], metric_definitions=[],
            series_summaries=digest,
        )
    assert editor_input["sections_raw"][0]["series_summary"] == digest["macro"]
