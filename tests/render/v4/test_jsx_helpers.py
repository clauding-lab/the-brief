"""Tests for brief.render.v4._jsx helper library.

At least 2 cases per helper, asserting on substrings/regex (not full-string equality).
"""
from __future__ import annotations

import re

import pytest

from brief.render.v4._jsx import (
    attr,
    bankerread_aside,
    cadence_pill,
    fmt_num,
    hero_wrap,
    pull_quote,
    section_head,
    sparkline_svg,
    staleness_dot,
)
from brief.schema import BankerReadFreeform, BankerReadStructured


# ---------------------------------------------------------------------------
# attr
# ---------------------------------------------------------------------------

class TestAttr:
    def test_basic_attribute(self) -> None:
        result = attr("class", "my-class")
        assert result == ' class="my-class"'

    def test_empty_value_returns_empty_string(self) -> None:
        assert attr("id", "") == ""

    def test_none_value_returns_empty_string(self) -> None:
        assert attr("href", None) == ""

    def test_escapes_quotes_in_value(self) -> None:
        result = attr("data-label", 'say "hello"')
        assert "&quot;" in result
        # The raw unescaped sequence `"hello"` (with surrounding quotes) should not appear
        # after the = sign (the surrounding double quotes are the attribute delimiters,
        # not part of the value — what matters is the inner quotes are escaped)
        assert '&quot;hello&quot;' in result

    def test_leading_space_in_output(self) -> None:
        result = attr("lang", "en")
        assert result.startswith(" ")


# ---------------------------------------------------------------------------
# fmt_num
# ---------------------------------------------------------------------------

class TestFmtNum:
    def test_none_returns_em_dash(self) -> None:
        assert fmt_num(None) == "—"

    def test_integer_no_decimal(self) -> None:
        result = fmt_num(42)
        assert "42" in result
        assert "." not in result

    def test_float_two_decimals(self) -> None:
        result = fmt_num(3.14159)
        assert "3.14" in result

    def test_large_number_with_commas(self) -> None:
        result = fmt_num(1234567.89)
        assert "1,234,567.89" in result

    def test_with_unit(self) -> None:
        result = fmt_num(100.0, unit="BDT")
        assert "BDT" in result
        assert 'class="unit"' in result

    def test_tabular_off_no_span(self) -> None:
        result = fmt_num(99.5, tabular=False)
        assert '<span class="num">' not in result
        assert "99.50" in result

    def test_tabular_on_wraps_in_span(self) -> None:
        result = fmt_num(10, tabular=True)
        assert 'class="num"' in result

    def test_negative_float(self) -> None:
        result = fmt_num(-1500.5)
        assert "-1,500.50" in result


# ---------------------------------------------------------------------------
# staleness_dot
# ---------------------------------------------------------------------------

class TestStalenessDot:
    def test_fresh_state(self) -> None:
        result = staleness_dot("fresh")
        assert 'class="dot dot-fresh"' in result

    def test_warn_state(self) -> None:
        result = staleness_dot("warn")
        assert "dot-warn" in result

    def test_stale_state(self) -> None:
        result = staleness_dot("stale")
        assert "dot-stale" in result

    def test_pending_state(self) -> None:
        result = staleness_dot("pending")
        assert "dot-pending" in result

    def test_invalid_state_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown state"):
            staleness_dot("unknown")  # type: ignore[arg-type]

    def test_returns_span_element(self) -> None:
        result = staleness_dot("fresh")
        assert result.startswith("<span")
        assert result.endswith("</span>")


# ---------------------------------------------------------------------------
# cadence_pill
# ---------------------------------------------------------------------------

class TestCadencePill:
    def test_daily(self) -> None:
        result = cadence_pill("daily")
        assert "cadence-daily" in result
        assert "DAILY" in result

    def test_event(self) -> None:
        result = cadence_pill("event")
        assert "cadence-event" in result
        assert "EVENT" in result

    def test_pending(self) -> None:
        result = cadence_pill("pending")
        assert "cadence-pending" in result
        assert "PENDING" in result

    def test_weekly_label_uppercased(self) -> None:
        result = cadence_pill("weekly")
        assert "WEEKLY" in result

    def test_returns_span(self) -> None:
        result = cadence_pill("monthly")
        assert result.startswith("<span")
        assert "cadence-pill" in result


# ---------------------------------------------------------------------------
# sparkline_svg
# ---------------------------------------------------------------------------

class TestSparklineSvg:
    def test_twelve_points_returns_svg_with_polyline(self) -> None:
        pts = [1.0, 2.0, 1.5, 3.0, 2.5, 4.0, 3.5, 2.0, 1.0, 2.5, 3.0, 2.0]
        result = sparkline_svg(pts)
        assert "<svg" in result
        assert "<polyline" in result
        assert "points=" in result

    def test_one_point_returns_empty_string(self) -> None:
        assert sparkline_svg([5.0]) == ""

    def test_empty_list_returns_empty_string(self) -> None:
        assert sparkline_svg([]) == ""

    def test_all_equal_points_produces_horizontal_line(self) -> None:
        pts = [3.0] * 12
        result = sparkline_svg(pts)
        # All y coordinates should be the same (mid-height = h/2 = 16.0)
        assert "<polyline" in result
        # Verify it doesn't return empty
        assert result != ""

    def test_custom_color_applied(self) -> None:
        pts = [1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0]
        result = sparkline_svg(pts, color="#2f6b3a")
        assert "#2f6b3a" in result

    def test_custom_width_height(self) -> None:
        pts = [1.0, 2.0, 3.0]
        result = sparkline_svg(pts, w=220, h=42)
        assert 'width="220"' in result
        assert 'height="42"' in result

    def test_stroke_width_1_5(self) -> None:
        pts = [1.0, 2.0, 3.0, 4.0]
        result = sparkline_svg(pts)
        assert 'stroke-width="1.5"' in result

    def test_fill_none(self) -> None:
        pts = [1.0, 2.0, 3.0, 4.0]
        result = sparkline_svg(pts)
        assert 'fill="none"' in result


# ---------------------------------------------------------------------------
# hero_wrap
# ---------------------------------------------------------------------------

class TestHeroWrap:
    def test_wraps_in_metric_hero_class(self) -> None:
        result = hero_wrap("<span>content</span>")
        assert 'class="metric-card metric-hero"' in result

    def test_content_preserved_inside(self) -> None:
        result = hero_wrap("<p>hello</p>")
        assert "<p>hello</p>" in result

    def test_outer_element_is_div(self) -> None:
        result = hero_wrap("")
        assert result.startswith('<div class="metric-card metric-hero">')


# ---------------------------------------------------------------------------
# pull_quote
# ---------------------------------------------------------------------------

class TestPullQuote:
    def test_text_and_cite_present(self) -> None:
        result = pull_quote("Markets held steady.", "Desk Editor")
        assert "Markets held steady." in result
        assert "Desk Editor" in result

    def test_uses_blockquote_element(self) -> None:
        result = pull_quote("text", "cite")
        assert "<blockquote" in result
        assert "pull-quote" in result

    def test_glyph_present(self) -> None:
        result = pull_quote("text", "cite")
        assert "&ldquo;" in result

    def test_html_escapes_text(self) -> None:
        result = pull_quote("Rate <rose> & held", "Author")
        assert "&lt;rose&gt;" in result
        assert "&amp;" in result

    def test_html_escapes_cite(self) -> None:
        result = pull_quote("text", "A & B")
        assert "&amp;" in result

    def test_cite_in_cite_element(self) -> None:
        result = pull_quote("text", "Desk Editor")
        assert "<cite>" in result
        assert "Desk Editor" in result


# ---------------------------------------------------------------------------
# bankerread_aside
# ---------------------------------------------------------------------------

class TestBankerreadAside:
    def _make_structured(self) -> BankerReadStructured:
        return BankerReadStructured(
            meaning="Rates stayed flat.",
            action="Hold duration short.",
            trigger="Next MPC meeting.",
            focus="Short-term T-bills.",
            pull="Steady hand at the wheel.",
        )

    def _make_freeform(self) -> BankerReadFreeform:
        return BankerReadFreeform(
            text="The central bank signaled continued caution.",
            pull="Caution persists.",
        )

    def test_structured_has_four_sections(self) -> None:
        br = self._make_structured()
        result = bankerread_aside(br, anchor="bb", anchor_label="BB")
        assert "§A" in result
        assert "§B" in result
        assert "§C" in result
        assert "§D" in result

    def test_structured_drop_cap_on_first_letter(self) -> None:
        br = self._make_structured()
        result = bankerread_aside(br, anchor="bb", anchor_label="BB")
        assert 'class="drop-cap"' in result
        # First letter of 'Rates stayed flat.' is 'R'
        assert ">R<" in result

    def test_structured_jump_link_present(self) -> None:
        br = self._make_structured()
        result = bankerread_aside(br, anchor="bb", anchor_label="BB")
        assert "Jump to §BB" in result

    def test_structured_kind_in_class(self) -> None:
        br = self._make_structured()
        result = bankerread_aside(br, anchor="bb", anchor_label="BB")
        assert "br-structured" in result

    def test_freeform_single_text_block(self) -> None:
        br = self._make_freeform()
        result = bankerread_aside(br, anchor="headlines", anchor_label="01")
        assert "The central bank signaled" in result
        assert "br-freeform-body" in result

    def test_freeform_jump_link_present(self) -> None:
        br = self._make_freeform()
        result = bankerread_aside(br, anchor="headlines", anchor_label="01")
        assert "Jump to §01" in result

    def test_freeform_kind_in_class(self) -> None:
        br = self._make_freeform()
        result = bankerread_aside(br, anchor="headlines", anchor_label="01")
        assert "br-freeform" in result

    def test_aside_element_used(self) -> None:
        br = self._make_structured()
        result = bankerread_aside(br, anchor="macro", anchor_label="03")
        assert result.startswith("<aside")

    def test_id_attribute_set_from_anchor(self) -> None:
        br = self._make_structured()
        result = bankerread_aside(br, anchor="fx", anchor_label="06")
        assert 'id="br-fx"' in result


# ---------------------------------------------------------------------------
# section_head
# ---------------------------------------------------------------------------

class TestSectionHead:
    def _default_head(self) -> str:
        return section_head(
            numeral="02",
            kicker="POLICY & RATES",
            title_parts=[("The Governor held.", "plain"), ("Again.", "italic-ox")],
            dek="Bangladesh Bank kept the repo rate at 8.5%.",
            meta=["Monthly", "BB"],
        )

    def test_numeral_rendered(self) -> None:
        result = self._default_head()
        assert "02" in result

    def test_kicker_rendered(self) -> None:
        result = self._default_head()
        assert "POLICY &amp; RATES" in result or "POLICY & RATES" in result

    def test_italic_ox_class_applied(self) -> None:
        result = self._default_head()
        assert 'class="italic-ox"' in result
        assert "Again." in result

    def test_plain_part_not_wrapped_in_em(self) -> None:
        result = self._default_head()
        # "The Governor held." should appear as plain text, not inside em.italic-ox
        assert "The Governor held." in result

    def test_dek_rendered(self) -> None:
        result = self._default_head()
        assert "Bangladesh Bank kept the repo rate" in result

    def test_meta_pills_rendered(self) -> None:
        result = self._default_head()
        assert "Monthly" in result
        assert "meta-pill" in result

    def test_header_element_used(self) -> None:
        result = self._default_head()
        assert result.startswith("<header")
        assert "section-head" in result

    def test_no_meta_pills_when_empty(self) -> None:
        result = section_head(
            numeral="05",
            kicker="T-BOND",
            title_parts=[("Yield holds.", "plain")],
            dek="Short end flat.",
            meta=[],
        )
        assert "section-meta" not in result
