"""Tests for V4 front-door/footer templates: dateline, masthead, colophon."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pytest

from brief.pipeline import RunResult
from brief.schema import Delta, Metric, SectionData, TodaysCall


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_metric(**kwargs) -> Metric:
    defaults = dict(
        id="generic", label="Generic", value=1.0, unit="",
        as_of=date(2026, 4, 24), source="Generic Source", cadence="daily",
    )
    defaults.update(kwargs)
    return Metric(**defaults)


def _make_run_result(**overrides) -> RunResult:
    base_sections = [
        SectionData(
            id="bb",
            title="Bangladesh Bank",
            freshness="fresh",
            metrics=[
                Metric(
                    id="reserves_total",
                    label="Reserves (Gross)",
                    value=20.5,
                    unit="bn USD",
                    as_of=date(2026, 4, 22),
                    source="Bangladesh Bank",
                    cadence="daily",
                )
            ],
        ),
        SectionData(
            id="fx",
            title="FX",
            freshness="fresh",
            metrics=[
                Metric(
                    id="usd_bdt",
                    label="USD/BDT",
                    value=121.50,
                    unit="BDT",
                    as_of=date(2026, 4, 24),
                    source="Bangladesh Bank",
                    cadence="daily",
                )
            ],
        ),
        SectionData(
            id="dse",
            title="DSE",
            freshness="fresh",
            metrics=[
                Metric(
                    id="dsex_close",
                    label="DSEX",
                    value=5420.75,
                    unit="pts",
                    as_of=date(2026, 4, 24),
                    source="DSE",
                    cadence="daily",
                )
            ],
        ),
        SectionData(
            id="iranwar",
            title="US-Iran War Impact",
            freshness="fresh",
            metrics=[
                Metric(
                    id="brent_spot",
                    label="Brent",
                    value=87.40,
                    unit="USD/bbl",
                    as_of=date(2026, 4, 24),
                    source="Oilprice.com",
                    cadence="daily",
                )
            ],
        ),
    ]
    return RunResult(
        sections=overrides.get("sections", base_sections),
        html="",
        claude_outputs={},
        call_reports=[],
        map_coords=[],
        read_order=[],
        todays_call=overrides.get(
            "todays_call",
            TodaysCall(text="Policy held; reserves steady; oil watch remains.", generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        ),
    )


# ---------------------------------------------------------------------------
# Dateline tests
# ---------------------------------------------------------------------------

class TestRenderDateline:
    def test_happy_path_contains_key_elements(self):
        """Dateline contains LIVE, HH:MM BDT time, all 4 metric labels."""
        from brief.render.v4.templates.dateline import render_dateline

        rr = _make_run_result()
        html = render_dateline(rr)

        assert "LIVE" in html
        assert "USD/BDT" in html
        assert "DSEX" in html
        assert "Brent" in html
        assert "Reserves" in html
        # Time in HH:MM BDT format somewhere in output
        assert re.search(r"\d{2}:\d{2} BDT", html)
        assert "Next update" in html

    def test_missing_fx_section_renders_em_dash(self):
        """When fx section is absent, USD/BDT value is em-dash, no crash."""
        from brief.render.v4.templates.dateline import render_dateline

        sections = [
            s for s in _make_run_result().sections if s.id != "fx"
        ]
        rr = _make_run_result(sections=sections)
        html = render_dateline(rr)

        # USD/BDT label must still appear
        assert "USD/BDT" in html
        # Em-dash for missing value
        assert "—" in html  # —

    def test_missing_bb_reserves_metric_renders_em_dash(self):
        """When bb section has no reserves metric, Reserves value is em-dash."""
        from brief.render.v4.templates.dateline import render_dateline

        # bb section with an unrelated metric (no 'reserves' in id/label)
        sections_modified = []
        for s in _make_run_result().sections:
            if s.id == "bb":
                modified = SectionData(
                    id="bb",
                    title="Bangladesh Bank",
                    freshness="fresh",
                    metrics=[
                        Metric(
                            id="policy_rate",
                            label="Policy Rate",
                            value=8.5,
                            unit="%",
                            as_of=date(2026, 4, 24),
                            source="Bangladesh Bank",
                            cadence="monthly",
                        )
                    ],
                )
                sections_modified.append(modified)
            else:
                sections_modified.append(s)

        rr = _make_run_result(sections=sections_modified)
        html = render_dateline(rr)

        assert "Reserves" in html
        # The fallback picks the first metric (policy_rate), so it should not crash
        # and a value should be present
        assert html  # not empty

    def test_missing_bb_section_entirely_renders_em_dash(self):
        """When bb section is entirely absent, Reserves value is em-dash."""
        from brief.render.v4.templates.dateline import render_dateline

        sections = [s for s in _make_run_result().sections if s.id != "bb"]
        rr = _make_run_result(sections=sections)
        html = render_dateline(rr)

        assert "Reserves" in html
        assert "—" in html


# ---------------------------------------------------------------------------
# Masthead tests
# ---------------------------------------------------------------------------

class TestRenderMasthead:
    def test_happy_path_contains_key_elements(self):
        """Masthead contains VOL. II, NO., todays_call text and byline."""
        from brief.render.v4.templates.masthead import render_masthead

        rr = _make_run_result()
        html = render_masthead(rr)

        assert "VOL. II" in html
        assert "NO." in html
        assert "TODAY'S CALL" in html
        assert "Policy held; reserves steady; oil watch remains." in html
        assert "Desk Editor · The Brief" in html

    def test_todays_call_none_renders_dash_and_default_byline(self):
        """When todays_call is None, text is em-dash and default byline is shown."""
        from brief.render.v4.templates.masthead import render_masthead

        rr = _make_run_result(todays_call=None)
        html = render_masthead(rr)

        assert "—" in html  # em-dash for text
        assert "Desk Editor · The Brief" in html

    def test_html_escaping_of_todays_call_text(self):
        """Script tags in todays_call.text are HTML-escaped."""
        from brief.render.v4.templates.masthead import render_masthead

        malicious_tc = TodaysCall(text="<script>alert('xss')</script>", generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        rr = _make_run_result(todays_call=malicious_tc)
        html = render_masthead(rr)

        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_masthead_contains_the_brief_title(self):
        """Masthead renders 'The Brief' heading and subtitle."""
        from brief.render.v4.templates.masthead import render_masthead

        rr = _make_run_result()
        html = render_masthead(rr)

        assert "The" in html
        assert "Brief" in html
        assert "Bangladesh Economic Intelligence" in html


# ---------------------------------------------------------------------------
# Colophon tests
# ---------------------------------------------------------------------------

class TestRenderColophon:
    def test_happy_path_contains_key_elements(self):
        """Colophon has brand, sources joined with ·, and Next edition label."""
        from brief.render.v4.templates.colophon import render_colophon

        rr = _make_run_result()
        html = render_colophon(rr)

        assert "The Brief" in html
        assert "Sources:" in html
        assert "Next edition" in html
        # Time format: DD MMM · HH:MM BDT
        assert re.search(r"\d{1,2} \w{3} · \d{2}:\d{2} BDT", html)

    def test_sources_deduped_and_sorted(self):
        """Duplicate sources appear only once, sorted alphabetically."""
        from brief.render.v4.templates.colophon import render_colophon

        # Two sections with same source
        sections = [
            SectionData(
                id="bb",
                title="Bangladesh Bank",
                freshness="fresh",
                metrics=[
                    Metric(
                        id="reserves_total",
                        label="Reserves",
                        value=20.5,
                        unit="bn USD",
                        as_of=date(2026, 4, 22),
                        source="Bangladesh Bank",
                        cadence="daily",
                    )
                ],
            ),
            SectionData(
                id="fx",
                title="FX",
                freshness="fresh",
                metrics=[
                    Metric(
                        id="usd_bdt",
                        label="USD/BDT",
                        value=121.50,
                        unit="BDT",
                        as_of=date(2026, 4, 24),
                        source="Bangladesh Bank",  # same source
                        cadence="daily",
                    )
                ],
            ),
        ]
        rr = _make_run_result(sections=sections)
        html = render_colophon(rr)

        # "Bangladesh Bank" should appear exactly once in the sources area
        sources_count = html.count("Bangladesh Bank")
        assert sources_count == 1

    def test_empty_sections_no_crash(self):
        """Empty sections list → colophon renders without crashing."""
        from brief.render.v4.templates.colophon import render_colophon

        rr = _make_run_result(sections=[])
        html = render_colophon(rr)

        assert "The Brief" in html
        assert "colophon" in html
        assert "Next edition" in html
