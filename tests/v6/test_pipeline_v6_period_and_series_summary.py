"""P2 fact-checker (2026-08-22 audit #204) — items 2 & 3:
  - every metric in `_to_v6_raw`'s output carries a deterministic `period`
  - a pre-editor `series_summary` digest is fetched and stamped per section,
    without disturbing the post-editor `_stamp_chart_series` full-series stamp
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from brief.pipeline_v6 import (
    _build_editor_input,
    _check_daily_as_of_vs_series_summary,
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
    # A 3-month window does not reach back a year, so the year-ago pair is
    # None — the digest's full shape, pinned exactly.
    assert out == {
        "dsex": {
            "n": 3, "first_ts": "2026-06-01", "first_value": 5000.0,
            "last_ts": "2026-08-01", "last_value": 5100.0,
            "min": 5000.0, "max": 5200.0,
            "value_1y_ago": None, "ts_1y_ago": None,
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


def _monthly_points(key: str, start: date, values: list[float]) -> list[SeriesPointV6]:
    """One point per calendar month from `start`, ascending."""
    points: list[SeriesPointV6] = []
    y, m = start.year, start.month
    for v in values:
        points.append(SeriesPointV6(key=key, ts=date(y, m, 1).isoformat(), value=v))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return points


def test_summarize_series_points_adds_year_ago_point():
    """Issue 207/208's "a year earlier" defect: the digest exposed only
    first/last/min/max, so the editor reached for `first_value` — the START of
    a 24-month window (9.95, Aug 2024) — and called it "a year earlier". The
    true 12-months-back point is 9.77 (Jul 2025). Both must now be citable,
    and they must stay DISTINCT."""
    values = [
        9.95, 9.90, 9.86, 9.84, 9.82, 9.80,   # Aug 2024 - Jan 2025
        9.79, 9.78, 9.78, 9.77, 9.77, 9.77,   # Feb 2025 - Jul 2025
        9.70, 9.62, 9.55, 9.48, 9.40, 9.33,   # Aug 2025 - Jan 2026
        9.25, 9.18, 9.10, 9.02, 8.95, 8.88,   # Feb 2026 - Jul 2026
    ]
    points = _monthly_points("cpi_12m_avg_monthly", date(2024, 8, 1), values)
    assert len(points) == 24

    digest = summarize_series_points(points)["cpi_12m_avg_monthly"]

    assert digest["first_value"] == 9.95           # the window START, unchanged
    assert digest["first_ts"] == "2024-08-01"
    assert digest["last_ts"] == "2026-07-01"
    # The honest "a year earlier" point — Jul 2025, exactly 365 days back.
    assert digest["value_1y_ago"] == 9.77
    assert digest["ts_1y_ago"] == "2025-07-01"
    assert digest["value_1y_ago"] != digest["first_value"]


def test_year_ago_is_none_when_window_too_short():
    """A window that does not reach back a year yields NO year-ago point —
    never the nearest-available substitute, which is exactly the first_value
    misread this field exists to replace."""
    points = _monthly_points("cpi_12m_avg_monthly", date(2026, 2, 1), [9.4, 9.3, 9.2, 9.1, 9.0, 8.9])
    digest = summarize_series_points(points)["cpi_12m_avg_monthly"]

    assert digest["n"] == 6
    assert digest["value_1y_ago"] is None
    assert digest["ts_1y_ago"] is None


def test_year_ago_point_tolerates_a_ragged_monthly_grid():
    """Real monthly series are stamped month-START or month-END inconsistently,
    so an exact 365-day hit is not guaranteed — a point within the tolerance
    window still counts, one far outside it does not."""
    near = [
        SeriesPointV6(key="k", ts="2025-07-31", value=4.4),   # 30 days off target
        SeriesPointV6(key="k", ts="2026-01-31", value=4.1),
        SeriesPointV6(key="k", ts="2026-06-30", value=3.9),
    ]
    assert summarize_series_points(near)["k"]["value_1y_ago"] == 4.4

    far = [
        SeriesPointV6(key="k", ts="2025-01-31", value=4.4),   # ~150 days off target
        SeriesPointV6(key="k", ts="2026-06-30", value=3.9),
    ]
    assert summarize_series_points(far)["k"]["value_1y_ago"] is None


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


# ─── daily as_of-vs-series tripwire (issue 206, defect a+b net) ────────────


def test_daily_metric_as_of_matches_its_sections_series_last_ts():
    """Issue 206 regression: the DSEX close tile's as_of (24 Aug, the RUN
    date) disagreed with its own chart's newest plotted point (23 Aug, the
    real session) — nothing anywhere flagged the two disagreeing. WARN-mode
    only: a legitimately lagging chart series must never hold the publish.
    """
    raw_sections = [{
        "slug": "dse",
        "metrics": [{"id": "dsex", "label": "DSEX close", "cadence": "daily",
                     "as_of": "2026-08-24"}],
        "series_summary": {
            "dsex": {"n": 5, "first_ts": "2026-08-19", "first_value": 5786.08,
                      "last_ts": "2026-08-23", "last_value": 5722.21464,
                      "min": 5722.21464, "max": 5786.08},
        },
    }]
    warnings = _check_daily_as_of_vs_series_summary(raw_sections)
    assert len(warnings) == 1
    assert "dsex" in warnings[0]
    assert "2026-08-24" in warnings[0]
    assert "2026-08-23" in warnings[0]


def test_daily_metric_as_of_matching_its_series_last_ts_produces_no_warning():
    raw_sections = [{
        "slug": "dse",
        "metrics": [{"id": "dsex", "label": "DSEX close", "cadence": "daily",
                     "as_of": "2026-08-23"}],
        "series_summary": {"dsex": {"last_ts": "2026-08-23"}},
    }]
    assert _check_daily_as_of_vs_series_summary(raw_sections) == []


def test_daily_as_of_check_ignores_non_daily_cadence():
    """Only cadence='daily' metrics are checked — a monthly CPI card legitimately
    naming a different month than its chart's newest point is defect (4)'s
    concern (card-vs-chart honesty), a separate FAIL-mode check."""
    raw_sections = [{
        "slug": "macro",
        "metrics": [{"id": "cpi_p2p_food_monthly", "label": "CPI Food (P-to-P)",
                     "cadence": "monthly", "as_of": "2026-06-30"}],
        "series_summary": {"cpi_p2p_food_monthly": {"last_ts": "2026-07-01"}},
    }]
    assert _check_daily_as_of_vs_series_summary(raw_sections) == []


def test_daily_as_of_check_ignores_metric_with_no_matching_series_key():
    """A daily metric whose id doesn't appear in series_summary (no chart for
    it, or the pre-editor digest fetch degraded) is silently skipped — this
    is a comparison check, not a presence check."""
    raw_sections = [{
        "slug": "dse",
        "metrics": [{"id": "dse_turnover_crore", "label": "Turnover",
                     "cadence": "daily", "as_of": "2026-08-24"}],
        "series_summary": {"dsex": {"last_ts": "2026-08-23"}},
    }]
    assert _check_daily_as_of_vs_series_summary(raw_sections) == []


# ─── dse session-low history fact (issues 205-208) ────────────────────────
#
# `dse` emits NO history_facts, so "a ten-session low" was editor-invented —
# byte-identical across issues 205-208 while the true rank ran 38 / 41 / 42.
# The rank is computable from the dsex series the pipeline already fetches.


def _daily_points(key: str, start: date, values: list[float]) -> list[SeriesPointV6]:
    """One point per calendar day from `start`, ascending. Calendar gaps are
    irrelevant to a SESSION count — the rank counts points, not days."""
    return [
        SeriesPointV6(key=key, ts=(start + timedelta(days=i)).isoformat(), value=v)
        for i, v in enumerate(values)
    ]


def _dsex_points_for_a_42_session_low() -> list[SeriesPointV6]:
    """The real DSEX tail from issues 206-208 (20-25 Aug 2026 closes) sitting on
    top of a run of higher closes, arranged so the most recent LOWER close sits
    EXACTLY 42 points back from the 25 Aug endpoint — the rank the investigation
    measured for that session.

    Walking back from 5,640.09: 5,643.57 / 5,722.21 / 5,786.08 (k=1..3), then
    38 higher padded closes (k=4..41), then 5,601.44 at k=42.
    """
    padding = _daily_points("dsex", date(2026, 6, 15), [5900.0] * 5)
    last_lower = [SeriesPointV6(key="dsex", ts="2026-06-22", value=5601.44)]
    higher_run = _daily_points(
        "dsex", date(2026, 6, 23), [5800.0 + i for i in range(38)]
    )
    tail = [
        SeriesPointV6(key="dsex", ts="2026-08-20", value=5786.08),
        SeriesPointV6(key="dsex", ts="2026-08-23", value=5722.21),
        SeriesPointV6(key="dsex", ts="2026-08-24", value=5643.57),
        SeriesPointV6(key="dsex", ts="2026-08-25", value=5640.09),
    ]
    return padding + last_lower + higher_run + tail


def test_sessions_since_lower_counts_back_to_the_last_lower_close():
    from brief.pipeline_v6 import _point_field, _sessions_since_lower

    points = _dsex_points_for_a_42_session_low()
    assert len(points) == 48
    assert _sessions_since_lower(points, _point_field) == 42


def test_sessions_since_lower_is_none_at_a_window_low():
    """A window low has NO lower predecessor — that must produce None, and
    therefore no fact, never a fabricated rank."""
    from brief.pipeline_v6 import _point_field, _sessions_since_lower

    points = _daily_points("dsex", date(2026, 6, 1), [6000.0 + i for i in range(40)][::-1])
    assert points[-1].value == 6000.0
    assert _sessions_since_lower(points, _point_field) is None


def test_dsex_session_low_fact_reads_like_a_history_anchor():
    from brief.pipeline_v6 import _dsex_session_low_fact

    fact = _dsex_session_low_fact(_dsex_points_for_a_42_session_low())
    assert fact is not None
    assert fact.metric_id == "dsex"
    assert fact.kind == "since_lower"
    assert fact.phrase == "a 42-session low (5,601.44 on 22 Jun the last lower close)"
    assert fact.reference_value == 5601.44
    assert fact.reference_value_formatted == "5,601.44"
    assert fact.reference_as_of == "2026-06-22"


def test_no_fact_when_rank_below_min():
    """Rank 1 — the immediately preceding close was lower — is a degenerate
    anchor that fires on any single-session move. Same LOOKBACK_MIN floor
    `history_anchors.last_lower_than` applies."""
    from brief.pipeline_v6 import _dsex_session_low_fact

    points = _daily_points("dsex", date(2026, 6, 1), [5900.0] * 38 + [5600.0, 5640.09])
    assert _dsex_session_low_fact(points) is None


def test_no_fact_at_window_low():
    from brief.pipeline_v6 import _dsex_session_low_fact

    points = _daily_points("dsex", date(2026, 6, 1), [6000.0 + i for i in range(40)][::-1])
    assert _dsex_session_low_fact(points) is None


def test_no_fact_when_the_window_is_too_short():
    """Under MIN_DATA_POINTS['daily'] a "since" claim is nominal, not
    statistical — history_anchors' own threshold, applied here too."""
    from brief.pipeline_v6 import _dsex_session_low_fact

    points = _daily_points("dsex", date(2026, 8, 1), [5900.0] * 10 + [5640.09])
    assert _dsex_session_low_fact(points) is None


def test_dse_raw_section_carries_the_session_low_fact():
    """The fact must ride the EXISTING history-facts-verbatim contract — the
    same `history_facts` field macro's anchors travel in, so no editor-prompt
    change is needed for the editor to see it."""
    from brief.pipeline_v6 import _dsex_session_low_fact

    fact = _dsex_session_low_fact(_dsex_points_for_a_42_session_low())
    sections = [SectionData(id="dse", title="DSE Markets", freshness="fresh", metrics=[])]
    raw = _to_v6_raw(
        sections, today=date(2026, 8, 25), extra_history_facts={"dse": [fact]}
    )

    facts = raw[0]["history_facts"]
    assert len(facts) == 1
    assert facts[0]["metric_id"] == "dsex"
    assert facts[0]["kind"] == "since_lower"
    assert facts[0]["phrase"] == "a 42-session low (5,601.44 on 22 Jun the last lower close)"
    assert facts[0]["reference_value_formatted"] == "5,601.44"
    assert facts[0]["reference_as_of"] == "2026-06-22"


def test_fetch_series_summaries_emits_the_dse_fact_from_the_series_it_already_fetched():
    """No second fetch: the rank is computed off the SAME dsex point array the
    dse digest is built from (landmine 23's spirit — one fetch, many uses)."""
    facts: dict[str, list] = {}
    with patch("brief.pipeline_v6.chart_series_fetcher.fetch_macro_cpi_series", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_remit_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_reserves_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_yield_ladder_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_fx_balance_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_fiscal_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_dsex",
               return_value=(_dsex_points_for_a_42_session_low(), [])) as fetch_dsex, \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_brent", return_value=[]):
        out = _fetch_series_summaries(
            today=date(2026, 8, 25), http=object(),
            supabase_url="https://test.supabase.co", service_key="key",
            history_facts_out=facts,
        )

    fetch_dsex.assert_called_once()
    assert out["dse"]["dsex"]["last_value"] == 5640.09
    assert [f.phrase for f in facts["dse"]] == [
        "a 42-session low (5,601.44 on 22 Jun the last lower close)"
    ]


def test_fetch_series_summaries_emits_no_dse_fact_at_a_window_low():
    facts: dict[str, list] = {}
    window_low = _daily_points("dsex", date(2026, 6, 1), [6000.0 + i for i in range(40)][::-1])
    with patch("brief.pipeline_v6.chart_series_fetcher.fetch_macro_cpi_series", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_remit_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_reserves_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_yield_ladder_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_fx_balance_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_fiscal_monthly", return_value={}), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_dsex", return_value=(window_low, [])), \
         patch("brief.pipeline_v6.chart_series_fetcher.fetch_brent", return_value=[]):
        _fetch_series_summaries(
            today=date(2026, 8, 25), http=object(),
            supabase_url="https://test.supabase.co", service_key="key",
            history_facts_out=facts,
        )
    assert facts == {}


def test_build_editor_input_passes_derived_history_facts_to_the_raw_section():
    from brief.pipeline_v6 import _dsex_session_low_fact

    fact = _dsex_session_low_fact(_dsex_points_for_a_42_session_low())
    sections = [SectionData(id="dse", title="DSE Markets", freshness="fresh", metrics=[])]
    with patch("brief.pipeline_v6.fetch_max_issue_no", return_value=1):
        editor_input, _lens = _build_editor_input(
            sections, date(2026, 8, 25), [],
            previous_brief=None, previous_lens=None, recent_news=[], metric_definitions=[],
            derived_history_facts={"dse": [fact]},
        )
    dse_raw = next(s for s in editor_input["sections_raw"] if s["slug"] == "dse")
    assert [f["phrase"] for f in dse_raw["history_facts"]] == [
        "a 42-session low (5,601.44 on 22 Jun the last lower close)"
    ]


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
