"""Pre-editor held-over flagging — Patch 2 of fresh-brief V1 follow-up.

Bug context: Patch 1 fixed the lens-magnitude calc, but on quiet days
(every section's relative move <5%) the lens scorer falls back to
previous_lens, which has been "banking" forever. Editor then picks NPL as
the iconic banking metric, NPL ships as cover_metric for the third issue
running with held_from=null.

Fix: compute `is_held_over` for each metric BEFORE the editor call by
diffing value text against the previous brief, gated by cadence (only
quarterly/monthly metrics can be "held" — daily/weekly should be moving).
The flag flows into both:
  1. sections_for_lens (so signal_score correctly penalizes held metrics)
  2. editor_input["sections_raw"][i]["metrics"][j] (so the editor sees it)

The editor prompt then has a one-line rule: don't pick is_held_over=true
metrics as cover_metric.
"""
from datetime import date

import pytest

from brief import pipeline_v6
from brief.schema import Metric, SectionData


# ──────────────────────────────────────────────────────────────────────
# _compute_is_held_over — the deterministic flag
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cadence, curr_value, prev_value, expected",
    [
        # Quarterly + unchanged → held
        ("quarterly", "35.73%", "35.73%", True),
        # Monthly + unchanged → held
        ("monthly", "120.50", "120.50", True),
        # Daily + unchanged → NOT held (daily metrics SHOULD move; if they don't,
        # that's a freshness issue, not a held-over case)
        ("daily", "100", "100", False),
        # Weekly + unchanged → NOT held (same reasoning as daily)
        ("weekly", "100", "100", False),
        # Quarterly + changed → NOT held (it moved)
        ("quarterly", "35.73%", "30.0%", False),
        # Quarterly + no prev (cold start) → NOT held (nothing to compare)
        ("quarterly", "35.73%", None, False),
        # Event cadence + unchanged → NOT held (event metrics aren't periodic prints)
        ("event", "$50", "$50", False),
        # Empty cadence → NOT held (defensive — unknown cadence is treated as non-held)
        ("", "100", "100", False),
        # None cadence → NOT held
        (None, "100", "100", False),
    ],
)
def test_compute_is_held_over(cadence, curr_value, prev_value, expected):
    actual = pipeline_v6._compute_is_held_over(curr_value, prev_value, cadence)
    assert actual is expected, \
        f"cadence={cadence!r} curr={curr_value!r} prev={prev_value!r}: " \
        f"expected {expected}, got {actual}"


# ──────────────────────────────────────────────────────────────────────
# Integration: is_held_over flows through editor input + lens scorer
# ──────────────────────────────────────────────────────────────────────


def _make_previous_brief(banking_npl: str, iran_brent: str) -> dict:
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


def test_editor_input_marks_npl_held_over_when_unchanged_quarterly(monkeypatch):
    """The user-visible regression: Issue 91, 92 shipped NPL=35.73% (Q4 2025
    print, quarterly). When today's NPL is the same value, editor_input must
    expose `is_held_over=True` for that metric so the editor skips it for
    cover_metric."""
    monday = date(2026, 5, 4)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)

    previous = _make_previous_brief(banking_npl="35.73%", iran_brent="$107.56")

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
        fake_sections, monday, scraped_headlines=[],
        previous_brief=previous, previous_lens="banking",
        recent_news=[], metric_definitions=[],
    )

    raw_banking = next(s for s in editor_input["sections_raw"] if s["slug"] == "banking")
    npl_metric = raw_banking["metrics"][0]
    assert npl_metric["is_held_over"] is True, \
        "NPL Ratio (quarterly) with unchanged value must be flagged is_held_over=True " \
        f"in editor_input; got {npl_metric.get('is_held_over')!r}"

    # Brent (daily, value moved) must NOT be held
    raw_iran = next(s for s in editor_input["sections_raw"] if s["slug"] == "iran")
    brent_metric = raw_iran["metrics"][0]
    assert brent_metric["is_held_over"] is False, \
        f"Brent Spot (daily, moved) must not be held; got {brent_metric.get('is_held_over')!r}"


def test_editor_input_does_not_mark_held_when_npl_actually_moved(monkeypatch):
    """Symmetry: if NPL value changed (e.g., new Q1 2026 print), it's not held."""
    monday = date(2026, 5, 4)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)

    # NPL changed 30% → 35.73%
    previous = _make_previous_brief(banking_npl="30.0%", iran_brent="$113.95")

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
    ]

    editor_input, _ = pipeline_v6._build_editor_input(
        fake_sections, monday, scraped_headlines=[],
        previous_brief=previous, previous_lens="banking",
        recent_news=[], metric_definitions=[],
    )

    raw_banking = next(s for s in editor_input["sections_raw"] if s["slug"] == "banking")
    npl_metric = raw_banking["metrics"][0]
    assert npl_metric["is_held_over"] is False, \
        "NPL value moved 19% — must not be flagged held"


def test_lens_scorer_signal_drops_when_all_metrics_held(monkeypatch):
    """When every metric in a section is held-over, signal_score = 0 → that
    section's overall score = 0 (freshness × magnitude × signal). Combined
    with Patch 1's magnitude fix, this further demotes stuck-banking from the
    lens picker on quiet days."""
    monday = date(2026, 5, 4)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)

    # Banking NPL stuck (quarterly), Iran Brent moved (daily).
    previous = _make_previous_brief(banking_npl="35.73%", iran_brent="$107.56")

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

    # With banking marked is_held_over=True (signal=0) and iran daily moved
    # (signal=1.0, magnitude > 0), iran wins. Patch 1 already gives this on
    # this fixture; Patch 2 reinforces by zeroing banking's signal completely.
    assert today_lens == "iran", \
        f"banking should be demoted by held-over signal=0; got lens={today_lens!r}"


def test_editor_input_held_over_default_false_when_no_prev_brief(monkeypatch):
    """Cold start: no previous brief → no metric can be held-over (no prior
    print to compare to). All is_held_over=False."""
    monday = date(2026, 5, 4)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 0)

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
    ]

    editor_input, _ = pipeline_v6._build_editor_input(
        fake_sections, monday, scraped_headlines=[],
        previous_brief=None, previous_lens=None,
        recent_news=[], metric_definitions=[],
    )

    raw_banking = next(s for s in editor_input["sections_raw"] if s["slug"] == "banking")
    npl_metric = raw_banking["metrics"][0]
    assert npl_metric["is_held_over"] is False, \
        "Cold start: nothing can be held; got is_held_over=True"


def test_daily_metric_unchanged_value_not_marked_held(monkeypatch):
    """Daily/weekly metrics never count as held-over even if value is
    momentarily identical — they're supposed to move. A repeated value
    means the data is stale (a freshness issue), not a held-over case.
    """
    monday = date(2026, 5, 4)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)

    # Brent unchanged at $113.95 (daily metric, should be moving)
    previous = _make_previous_brief(banking_npl="35.73%", iran_brent="$113.95")

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
    ]

    editor_input, _ = pipeline_v6._build_editor_input(
        fake_sections, monday, scraped_headlines=[],
        previous_brief=previous, previous_lens="iran",
        recent_news=[], metric_definitions=[],
    )

    raw_iran = next(s for s in editor_input["sections_raw"] if s["slug"] == "iran")
    brent_metric = raw_iran["metrics"][0]
    assert brent_metric["is_held_over"] is False, \
        "Daily metric (Brent) must never be held even when value unchanged"
