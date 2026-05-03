"""TDD tests for warming_up freshness state.

Covers:
1. Schema — FreshnessKind accepts "warming_up"
2. Cadence — section_freshness_for_section() returns "warming_up" for the 6
   no-legacy sections when all their metrics have value=None (empty history)
3. Builders — all 6 no-legacy builders emit freshness="warming_up" when
   ctx.history returns None for all their metric_ids
4. Renderer — SectionData with freshness="warming_up" renders intentional
   placeholder copy, dot-warming-up class, and does NOT render "Section Unavailable"
"""
from __future__ import annotations

import importlib
from datetime import date
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.cadence import section_freshness, SECTIONS_WITHOUT_LEGACY_BACKFILL
from brief.schema import FreshnessKind, Metric, SectionData
from brief.render.v4.templates._generic import render_generic_section, _SECTION_META


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

TODAY = date(2026, 4, 25)


def _null_metric(mid: str, cadence: str = "monthly") -> Metric:
    """A metric whose value is None — simulates empty history."""
    return Metric(
        id=mid, label=mid, value=None, unit="%",
        as_of=TODAY, source="test", cadence=cadence,  # type: ignore[arg-type]
    )


def _empty_history_ctx() -> BuilderContext:
    """BuilderContext where history.get_latest() always returns None."""
    snapshot = MagicMock()
    history = MagicMock()
    history.get_latest.return_value = None
    return BuilderContext(snapshot=snapshot, history=history, today=TODAY)


# ---------------------------------------------------------------------------
# 1. Schema — "warming_up" is a valid FreshnessKind literal
# ---------------------------------------------------------------------------

class TestSchemaFreshnessKind:
    def test_warming_up_is_valid_freshness_kind(self) -> None:
        """SectionData should accept freshness='warming_up' without validation error."""
        section = SectionData(
            id="banking",
            title="Banking",
            metrics=[],
            freshness="warming_up",
        )
        assert section.freshness == "warming_up"

    def test_warming_up_round_trips_model_dump(self) -> None:
        section = SectionData(
            id="macro", title="Macro", metrics=[], freshness="warming_up"
        )
        dumped = section.model_dump()
        assert dumped["freshness"] == "warming_up"


# ---------------------------------------------------------------------------
# 2. Cadence — SECTIONS_WITHOUT_LEGACY_BACKFILL constant + section_freshness
#    returns "warming_up" for those sections when all metrics are None-valued
# ---------------------------------------------------------------------------

class TestSectionsWithoutLegacyBackfill:
    def test_constant_contains_exactly_six_sections(self) -> None:
        assert SECTIONS_WITHOUT_LEGACY_BACKFILL == {
            "banking", "macro", "dam", "remit", "fiscal", "nbr"
        }

    def test_does_not_contain_backfilled_sections(self) -> None:
        """dse, tbond, comm have legacy backfill — must NOT be in the set."""
        for sid in ("dse", "tbond", "comm"):
            assert sid not in SECTIONS_WITHOUT_LEGACY_BACKFILL


class TestSectionFreshnessWarmingUp:
    """section_freshness variant that accepts a section_id uses warming_up."""

    def _null_metrics_list(self) -> list[Metric]:
        return [_null_metric("x"), _null_metric("y")]

    @pytest.mark.parametrize("sid", ["banking", "macro", "dam", "remit", "fiscal", "nbr"])
    def test_no_legacy_sections_return_warming_up(self, sid: str) -> None:
        metrics = self._null_metrics_list()
        result = section_freshness(metrics, today=TODAY, section_id=sid)
        assert result == "warming_up"

    @pytest.mark.parametrize("sid", ["dse", "tbond", "comm", "bb", "fx"])
    def test_other_sections_still_return_unavailable(self, sid: str) -> None:
        metrics = self._null_metrics_list()
        result = section_freshness(metrics, today=TODAY, section_id=sid)
        assert result == "unavailable"

    def test_section_id_none_returns_unavailable(self) -> None:
        """Legacy call without section_id → unavailable (backwards-compatible)."""
        metrics = self._null_metrics_list()
        result = section_freshness(metrics, today=TODAY)
        assert result == "unavailable"

    def test_stale_still_wins_over_warming_up(self) -> None:
        """If history exists but is stale, stale wins — not warming_up."""
        stale_metric = Metric(
            id="x", label="x", value=1.0, unit="%",
            as_of=date(2025, 1, 1), source="t", cadence="monthly",
        )
        result = section_freshness([stale_metric], today=TODAY, section_id="banking")
        assert result == "stale"

    def test_warning_still_wins_over_warming_up(self) -> None:
        """If history exists but is warning, warning wins — not warming_up."""
        warn_metric = Metric(
            id="x", label="x", value=1.0, unit="%",
            as_of=date(2026, 3, 5), source="t", cadence="monthly",
        )
        result = section_freshness([warn_metric], today=TODAY, section_id="banking")
        # 51 days — monthly stale threshold >45 → stale
        assert result in ("stale", "warning")
        assert result != "warming_up"


# ---------------------------------------------------------------------------
# 3. Builders — all 6 emit freshness="warming_up" with empty history
# ---------------------------------------------------------------------------

_NO_LEGACY_BUILDERS = ["banking", "macro", "dam", "remit", "fiscal", "nbr"]


@pytest.mark.parametrize("bid", _NO_LEGACY_BUILDERS)
def test_builder_emits_warming_up_when_history_empty(bid: str) -> None:
    """Builder for a no-legacy section should return freshness='warming_up'
    when history.get_latest() returns None for all metric_ids."""
    mod = importlib.import_module(f"brief.builders.{bid}")
    ctx = _empty_history_ctx()
    section = mod.build(ctx)
    assert isinstance(section, SectionData)
    assert section.freshness == "warming_up", (
        f"Builder '{bid}' returned freshness={section.freshness!r}, expected 'warming_up'"
    )


@pytest.mark.parametrize("bid", ["dse", "tbond", "comm"])
def test_backfilled_builder_is_not_warming_up(bid: str) -> None:
    """Backfill-capable sections must NOT emit warming_up."""
    mod = importlib.import_module(f"brief.builders.{bid}")
    ctx = _empty_history_ctx()
    section = mod.build(ctx)
    assert isinstance(section, SectionData)
    assert section.freshness != "warming_up", (
        f"Builder '{bid}' incorrectly emitted warming_up"
    )


# ---------------------------------------------------------------------------
# 4. Renderer — warming_up section renders intentional placeholder, not error
# ---------------------------------------------------------------------------

def _make_warming_up_section(sid: str) -> SectionData:
    return SectionData(
        id=sid,
        title=f"Test {sid}",
        metrics=[_null_metric(f"{sid}_x")],
        freshness="warming_up",
    )


class TestRenderWarmingUp:
    """render_generic_section renders a warming_up placeholder."""

    def _render(self, sid: str = "banking") -> str:
        section = _make_warming_up_section(sid)
        meta = _SECTION_META[sid]
        return render_generic_section(
            section,
            dom_id=f"section-{sid}",
            numeral=meta[0],
            kicker=meta[1],
            title=meta[2],
            bankerread_label=f"§{meta[0]} {meta[2]}",
        )

    def test_does_not_render_section_unavailable(self) -> None:
        html = self._render("banking")
        assert "Section Unavailable" not in html

    def test_renders_building_copy(self) -> None:
        html = self._render("banking")
        assert "Building" in html

    def test_renders_dot_warming_up_class(self) -> None:
        html = self._render("banking")
        assert "dot-warming-up" in html

    def test_renders_fresh_pill_warming_up_class(self) -> None:
        html = self._render("banking")
        assert "warming-up" in html

    def test_section_wrapper_is_present(self) -> None:
        html = self._render("banking")
        assert 'id="section-banking"' in html
        assert "<section" in html

    def test_does_not_contain_section_unavailable_class(self) -> None:
        html = self._render("macro")
        assert "section-unavailable" not in html

    @pytest.mark.parametrize("sid", _NO_LEGACY_BUILDERS)
    def test_all_six_sections_render_warming_up(self, sid: str) -> None:
        html = self._render(sid)
        assert "Section Unavailable" not in html
        assert "dot-warming-up" in html

    def test_warming_up_contains_return_date(self) -> None:
        """Placeholder should mention a date 7 days out from today."""
        html = self._render("banking")
        # The date 7 days after TODAY (2026-04-25) is 2026-05-02
        assert "2026-05-02" in html


class TestStalenesssDotWarmingUp:
    """staleness_dot accepts 'warming_up' state."""

    def test_staleness_dot_warming_up(self) -> None:
        from brief.render.v4._jsx import staleness_dot
        result = staleness_dot("warming_up")
        assert "dot-warming-up" in result

    def test_staleness_dot_warming_up_is_span(self) -> None:
        from brief.render.v4._jsx import staleness_dot
        result = staleness_dot("warming_up")
        assert result.startswith("<span")
        assert result.endswith("</span>")


class TestFreshnessPillWarmingUp:
    """_freshness_pill_html renders an intentional amber/informational pill."""

    def test_freshness_pill_warming_up_text(self) -> None:
        from brief.render.v4.templates._generic import _freshness_pill_html
        result = _freshness_pill_html("warming_up")
        assert result != ""
        # Should NOT use the red/error styling (stale class)
        # Should use an informational class: warming-up
        assert "warming-up" in result

    def test_freshness_pill_warming_up_contains_building(self) -> None:
        from brief.render.v4.templates._generic import _freshness_pill_html
        result = _freshness_pill_html("warming_up")
        # Pill text should convey "building" or "warming"
        lower = result.lower()
        assert "building" in lower or "warming" in lower
