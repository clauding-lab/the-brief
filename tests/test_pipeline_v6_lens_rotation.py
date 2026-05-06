"""Lens-rotation regression tests — Patch 1 of fresh-brief V1 follow-up.

Bug being fixed: the V5 builders don't populate Metric.delta (only bb_reserves
does), so `_delta_sigma` reads None for every metric → magnitude=0.0 for every
section → all sections tie at score=0.0 → quiet_day_alpha picks "banking"
alphabetically → editor picks NPL as iconic banking metric → NPL repeats
across consecutive issues even when its value hasn't moved.

Fix: when `Metric.delta` is missing, fall back to diffing the metric's value
text against the previous brief's same (slug, label). This makes the lens
rotate based on actual movement.
"""
from datetime import date

import pytest

from brief import pipeline_v6
from brief.builders.lens import score_lens


# ──────────────────────────────────────────────────────────────────────
# _diff_value_to_sigma — string-tolerant numeric diff helper
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "curr, prev, expected",
    [
        # Identical → 0.0 (the failure mode that produced NPL repeats)
        ("35.73%", "35.73%", 0.0),
        ("$113.95", "$113.95", 0.0),
        # Percent values
        pytest.param("35.73%", "30.0%", 0.191, id="pct-up-19pct"),
        pytest.param("28.5%", "30.0%", 0.05, id="pct-down-5pct"),
        # Currency with $ prefix
        pytest.param("$113.95", "$108.17", 0.0534, id="usd-up-5pct"),
        # BDT with currency symbol + comma thousands
        pytest.param("৳15,400", "৳15,200", 0.013, id="bdt-comma-up"),
        # Plain numeric strings
        pytest.param("123.45", "100", 0.2345, id="plain-numeric"),
        # Negative deltas have same magnitude as positive
        pytest.param("90", "100", 0.1, id="negative-delta"),
        # Unparseable curr → 0.0 (no false signal)
        ("n/a", "100", 0.0),
        # Unparseable prev → 0.0
        ("100", "n/a", 0.0),
        # Both None → 0.0 (cold start)
        (None, None, 0.0),
        # prev=None → 0.0 (no comparison possible)
        ("100", None, 0.0),
        # Tiny prev → returns abs(curr) when prev~0
        pytest.param("0.001", "0.0", 0.001, id="prev-zero-returns-abs-curr"),
        # Large move clamps to 1.0
        pytest.param("100", "1", 1.0, id="huge-move-clamped"),
    ],
)
def test_diff_value_to_sigma_parametrized(curr, prev, expected):
    actual = pipeline_v6._diff_value_to_sigma(curr, prev)
    assert actual == pytest.approx(expected, abs=0.01), \
        f"expected ~{expected} for ({curr!r}, {prev!r}), got {actual}"


# ──────────────────────────────────────────────────────────────────────
# _delta_sigma — should accept prev_value kwarg and use it as fallback
# ──────────────────────────────────────────────────────────────────────


def test_delta_sigma_uses_prev_value_when_delta_missing():
    """V5 metrics without a `delta` sub-object should still produce a non-zero
    sigma when the value differs from the previous brief."""
    metric = {"label": "NPL Ratio", "value": "30.0%"}  # no delta, no delta_pct
    sigma = pipeline_v6._delta_sigma(metric, [], prev_value="35.73%")
    assert sigma > 0.1, f"expected non-trivial sigma, got {sigma}"


def test_delta_sigma_zero_when_value_unchanged_vs_prev():
    """Identical value text → magnitude 0.0 (the NPL-repeat case)."""
    metric = {"label": "NPL Ratio", "value": "35.73%"}
    sigma = pipeline_v6._delta_sigma(metric, [], prev_value="35.73%")
    assert sigma == 0.0


def test_delta_sigma_prefers_explicit_delta_over_prev_diff():
    """When `Metric.delta.value` is set (e.g., bb_reserves), use that — don't
    overwrite with a prev-brief diff."""
    metric = {
        "label": "Reserves",
        "value": "$25.5B",
        "delta": {"value": 0.42, "direction": "up", "window": "wow"},
    }
    sigma = pipeline_v6._delta_sigma(metric, [], prev_value="$23.0B")
    # 0.42 (the explicit delta) should win, not the value-text diff (~10%)
    assert sigma == pytest.approx(0.42, abs=0.001)


def test_delta_sigma_falls_back_to_zero_when_no_signals():
    """No delta, no delta_pct, no prev_value → 0.0."""
    metric = {"label": "NPL Ratio", "value": "35.73%"}
    sigma = pipeline_v6._delta_sigma(metric, [])
    assert sigma == 0.0


def test_delta_sigma_falls_through_unparseable_delta_pct_to_prev_value():
    """If delta_pct is set but unparseable, the except clause should fall
    through to the prev_value branch instead of returning 0.0 prematurely."""
    metric = {"label": "X", "value": "35.73%", "delta_pct": "n/a"}
    sigma = pipeline_v6._delta_sigma(metric, [], prev_value="30.0%")
    assert sigma > 0.0, "delta_pct unparseable should fall through to prev-value diff"


# ──────────────────────────────────────────────────────────────────────
# Integration: lens rotation when banking is stuck + something else moves
# ──────────────────────────────────────────────────────────────────────


def _make_previous_brief(banking_npl: str, iran_brent: str) -> dict:
    """Minimal previous-brief shape that diff._index_previous_metrics consumes.

    Note: the prev-brief sections use V6 slugs ("iran"), while the SectionData
    fixtures below use V5 ids ("iranwar"). pipeline_v6._to_v6_raw maps V5 id →
    V6 slug via V5_TO_V6 before the lens scorer sees them, so the (slug, label)
    lookup against prev_metrics_idx hits correctly.
    """
    return {
        "brief": {"issue_no": 91, "lens": "banking", "frame": "credit-cycle"},
        "sections": [
            {
                "slug": "banking",
                "metrics": [{"label": "NPL Ratio", "value": banking_npl}],
                "news": [],
            },
            {
                "slug": "iran",
                "metrics": [{"label": "Brent Spot", "value": iran_brent}],
                "news": [],
            },
        ],
    }


def test_lens_rotates_off_banking_when_npl_stuck_and_brent_moves(monkeypatch):
    """The user-visible regression test:

    - Banking NPL is unchanged across two consecutive issues (35.73% → 35.73%).
    - Iran Brent spot moved meaningfully ($107.56 → $113.95, ~6% up).
    - Lens scorer should NOT pick banking; iran should win on magnitude.
    """
    monday = date(2026, 5, 4)

    previous = _make_previous_brief(banking_npl="35.73%", iran_brent="$107.56")

    # Mock all the supabase calls that _build_editor_input doesn't directly use
    # but pipeline_v6.run_publish would. We only call _build_editor_input here.
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)

    from brief.schema import Metric, SectionData

    fake_sections = [
        SectionData(
            id="banking", title="Banking", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="banking_npl_pct", label="NPL Ratio", value="35.73%",
                       unit="pct", as_of=date(2026, 1, 1), source="BB", cadence="quarterly"),
            ],
            news=[],
        ),
        SectionData(
            id="iranwar", title="External", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="iranwar_brent_spot", label="Brent Spot", value="$113.95",
                       unit="usd", as_of=monday, source="EconDelta", cadence="daily"),
            ],
            news=[],
        ),
    ]

    editor_input, today_lens = pipeline_v6._build_editor_input(
        fake_sections,
        monday,
        scraped_headlines=[],
        previous_brief=previous,
        previous_lens="banking",
        recent_news=[],
        metric_definitions=[],
    )

    # The fix: lens should be "iran" (banking is stuck), not "banking" (alphabetical fallback)
    assert today_lens == "iran", \
        f"expected lens to rotate to iran when banking NPL is stuck, got {today_lens!r}"

    # Sanity: today_lens is also baked into editor_input
    assert editor_input["today_lens"] == "iran"


def test_lens_picks_banking_when_npl_actually_moved(monkeypatch):
    """Symmetry: when banking NPL HAS moved, banking should win."""
    monday = date(2026, 5, 4)

    # NPL moved 30% → 35.73% (~19% relative move); Brent unchanged
    previous = _make_previous_brief(banking_npl="30.0%", iran_brent="$113.95")
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)

    from brief.schema import Metric, SectionData

    fake_sections = [
        SectionData(
            id="banking", title="Banking", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="banking_npl_pct", label="NPL Ratio", value="35.73%",
                       unit="pct", as_of=date(2026, 1, 1), source="BB", cadence="quarterly"),
            ],
            news=[],
        ),
        SectionData(
            id="iranwar", title="External", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="iranwar_brent_spot", label="Brent Spot", value="$113.95",
                       unit="usd", as_of=monday, source="EconDelta", cadence="daily"),
            ],
            news=[],
        ),
    ]

    _, today_lens = pipeline_v6._build_editor_input(
        fake_sections, monday, scraped_headlines=[],
        previous_brief=previous, previous_lens="banking",
        recent_news=[], metric_definitions=[],
    )

    assert today_lens == "banking", \
        f"expected banking when NPL moved 19%, got {today_lens!r}"


def test_lens_falls_back_when_no_previous_brief(monkeypatch):
    """Cold start (previous_brief=None): no movement signal at all → fallback
    to alphabetical. Same as today's behavior; we don't regress this path."""
    monday = date(2026, 5, 4)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)

    from brief.schema import Metric, SectionData

    fake_sections = [
        SectionData(
            id="iranwar", title="External", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="iranwar_brent_spot", label="Brent Spot", value="$113.95",
                       unit="usd", as_of=monday, source="EconDelta", cadence="daily"),
            ],
            news=[],
        ),
        SectionData(
            id="fx", title="FX", kicker="", tldr="", pull="",
            freshness="fresh", freshness_reason="",
            metrics=[
                Metric(id="fx_usd_bdt", label="USD/BDT", value="120.50",
                       unit="bdt", as_of=monday, source="BB", cadence="daily"),
            ],
            news=[],
        ),
    ]

    _, today_lens = pipeline_v6._build_editor_input(
        fake_sections, monday, scraped_headlines=[],
        previous_brief=None, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )

    # No previous brief → all sections at score=0 → alpha fallback. Of {fx, iran}, fx wins.
    assert today_lens == "fx", \
        f"cold start should fall back to alphabetical (fx); got {today_lens!r}"
