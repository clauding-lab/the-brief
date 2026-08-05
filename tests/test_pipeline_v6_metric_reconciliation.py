"""Deterministic post-editor metric reconciliation (sdf-diagnosis-2026-08-05.md §4).

`editor_v6.txt:49` grants the editor discretionary authority to reorder and
drop "low-signal" metrics, capped at 5 per section, and nothing downstream
ever validated what survived — an empty `metrics` list passes the V6 schema,
and the publisher writes whatever the editor returned verbatim. Across issues
175-186, §02 `bb` built 7 metrics and stored 5 every day: SDF reached
production in only 1 of 12 issues, SLF in 4 of 12. The editor also invented
tiles that exist in no builder ("Breadth" in §06 `dse`, issues 177-180).

Coverage:
  1. A protected metric (SDF) the editor dropped is re-injected from the raw
     builder output.
  2. Multiple missing protected metrics are re-injected in builder order.
  3. An editor-invented label with no counterpart in the raw builder output
     is rejected (dropped), closing the "Breadth" hole.
  4. A protected metric still absent after reconciliation (never built, or
     its whole section vanished) HARD-FAILS the pipeline — not log-only.
  5. Normal pass-through: an editor output matching the raw builder output
     exactly is left unchanged (no drops, no re-injections, no exception).
  6. Integration: brief.builders.bb's own `build()` output, fed through
     `_to_v6_raw`, reconciles correctly — proves the fix against the actual
     shape production code emits, not just a hand-built fixture.

Note: `PROTECTED_METRIC_IDS["bb"]` is checked unconditionally on every call
(mirrors production — `bb` is always in `sections_raw`, since even a builder
exception still yields a degraded `SectionData`, see brief/pipeline.py:90).
Tests that are not themselves about `bb` include a matching, already-healthy
`bb` raw/final pair so they exercise the section under test without also
tripping the corridor hard-fail path.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pytest

from brief import pipeline_v6
from brief.pipeline_v6 import MetricReconciliationError
from brief.v6_schema import BriefPayloadV6, BriefV6, MetricV6, SectionV6


# ─── Fixtures ──────────────────────────────────────────────────────────


def _make_section_v6(slug: str, metrics: list[MetricV6] | None = None) -> SectionV6:
    """Build a minimal valid SectionV6 for tests."""
    return SectionV6(
        slug=slug,
        ord=3,
        title=f"Section {slug.upper()}",
        group_key="banking",
        weight=1,
        metrics=metrics or [],
    )


def _make_brief_payload(sections: list[SectionV6]) -> BriefPayloadV6:
    """Wrap sections in a minimal valid BriefPayloadV6."""
    return BriefPayloadV6(
        brief=BriefV6(issue_no=186, volume=1, brief_date=date(2026, 8, 5)),
        sections=sections,
    )


def _raw_metric(metric_id: str, label: str, value: float, unit: str = "%") -> dict[str, Any]:
    """A minimal raw builder metric dict — the fields _reconcile_metrics reads
    off `sections_raw[i]["metrics"][j]` (a `Metric.model_dump()` entry)."""
    return {"id": metric_id, "label": label, "value": value, "unit": unit}


def _bb_raw_section(metrics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    full_corridor = [
        _raw_metric("bb_policy_rate", "Policy Rate", 9.50),
        _raw_metric("bb_sdf", "SDF", 7.50),
        _raw_metric("bb_slf", "SLF", 11.00),
        _raw_metric("bb_call_money", "Overnight Call Money", 9.48),
        _raw_metric("bb_gross_reserves", "Gross Reserves", 25.5, unit="bn USD"),
        _raw_metric("bb_call_money_7d", "Call Money · 7-day", 11.95),
        _raw_metric("bb_call_money_14d", "Call Money · 14-day", 9.48),
    ]
    return {"slug": "bb", "metrics": metrics if metrics is not None else full_corridor}


def _healthy_bb_pair() -> tuple[dict[str, Any], SectionV6]:
    """A `bb` raw/final pair where all three protected metrics already
    survived — safe "noise" for tests about a different section, so they
    don't also trip the corridor hard-fail check (see module docstring)."""
    raw = _bb_raw_section()
    final = _make_section_v6(
        "bb",
        metrics=[
            MetricV6(label="Policy Rate", value="9.50%"),
            MetricV6(label="SDF", value="7.50%"),
            MetricV6(label="SLF", value="11.00%"),
        ],
    )
    return raw, final


# ─── 1. Protected metric re-injected ────────────────────────────────────


def test_reconcile_reinjects_editor_dropped_protected_metric() -> None:
    """SDF was in the raw builder output but the editor dropped it — the
    section carries only the 5 metrics that survived storage. Reconciliation
    must re-inject SDF, formatted as a percent to match the corridor display.
    """
    raw_sections = [_bb_raw_section()]
    # Editor kept 5 of 7 — dropped SDF (index 1) and Gross Reserves (index 4),
    # matching issue 186's actual casualty list.
    stored = _make_section_v6(
        "bb",
        metrics=[
            MetricV6(label="Policy Rate", value="9.50%"),
            MetricV6(label="SLF", value="11.00%"),
            MetricV6(label="Overnight Call Money", value="9.48%"),
            MetricV6(label="Call Money · 7-day", value="11.95%"),
            MetricV6(label="Call Money · 14-day", value="9.48%"),
        ],
    )
    final_brief = _make_brief_payload([stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    labels = {m.label for m in final_brief.sections[0].metrics}
    assert "SDF" in labels
    sdf = next(m for m in final_brief.sections[0].metrics if m.label == "SDF")
    assert sdf.value == "7.50%"
    # Gross Reserves is NOT protected — the memo's protected set is the
    # corridor (policy/SDF/SLF) only — so it stays dropped; reconciliation
    # does not resurrect it.
    assert "Gross Reserves" not in labels


# ─── 2. Multiple missing protected metrics, builder order ──────────────


def test_reconcile_reinjects_multiple_missing_metrics_in_builder_order() -> None:
    """All three corridor metrics dropped by the editor — reconciliation
    re-injects all three, and the reinjected set appears in builder order
    (Policy Rate, then SDF, then SLF) relative to each other."""
    raw_sections = [_bb_raw_section()]
    stored = _make_section_v6(
        "bb",
        metrics=[
            MetricV6(label="Overnight Call Money", value="9.48%"),
            MetricV6(label="Gross Reserves", value="25.50 bn USD"),
        ],
    )
    final_brief = _make_brief_payload([stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    labels = [m.label for m in final_brief.sections[0].metrics]
    assert set(labels) == {
        "Overnight Call Money", "Gross Reserves", "Policy Rate", "SDF", "SLF",
    }
    # Reinjected metrics preserve builder order relative to each other.
    reinjected_order = [lbl for lbl in labels if lbl in {"Policy Rate", "SDF", "SLF"}]
    assert reinjected_order == ["Policy Rate", "SDF", "SLF"]


# ─── 3. Editor-invented label rejected ──────────────────────────────────


def test_reconcile_rejects_editor_invented_label() -> None:
    """The editor synthesised a "Breadth" tile with no counterpart in the
    builder's raw output (issues 177-180, §06 dse — merged from Advancing +
    Declining). Reconciliation must drop it; nothing built it, so nothing may
    publish it."""
    healthy_bb_raw, healthy_bb_final = _healthy_bb_pair()
    raw_sections = [
        healthy_bb_raw,
        {
            "slug": "dse",
            "metrics": [
                _raw_metric("dse_dsex_close", "DSEX Close", 5230.1, unit="pts"),
                _raw_metric("dse_advancing", "Advancing", 120, unit="count"),
                _raw_metric("dse_declining", "Declining", 80, unit="count"),
            ],
        },
    ]
    dse_stored = _make_section_v6(
        "dse",
        metrics=[
            MetricV6(label="DSEX Close", value="5,230.10 pts"),
            MetricV6(label="Breadth", value="120/80"),  # invented — no builder counterpart
        ],
    )
    final_brief = _make_brief_payload([healthy_bb_final, dse_stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    dse_section = next(s for s in final_brief.sections if s.slug == "dse")
    labels = {m.label for m in dse_section.metrics}
    assert labels == {"DSEX Close"}
    assert "Breadth" not in labels


# ─── 4. Hard fail when a protected metric is still absent ──────────────


def test_reconcile_hard_fails_when_protected_metric_never_built() -> None:
    """If the builder itself never emitted a protected id today (not just the
    editor dropping it), reconciliation has nothing to re-inject from and
    must HARD-FAIL — non-zero, no publish — rather than log and continue."""
    raw_sections = [
        _bb_raw_section(
            metrics=[
                _raw_metric("bb_policy_rate", "Policy Rate", 9.50),
                # bb_sdf and bb_slf never built this run (defensive case —
                # bb.py's own fallback normally prevents this, but reconcile
                # must not assume that holds forever)
                _raw_metric("bb_call_money", "Overnight Call Money", 9.48),
            ]
        )
    ]
    stored = _make_section_v6(
        "bb",
        metrics=[
            MetricV6(label="Policy Rate", value="9.50%"),
            MetricV6(label="Overnight Call Money", value="9.48%"),
        ],
    )
    final_brief = _make_brief_payload([stored])

    with pytest.raises(MetricReconciliationError) as exc_info:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    assert "bb.bb_sdf" in str(exc_info.value)
    assert "bb.bb_slf" in str(exc_info.value)


def test_reconcile_hard_fails_when_section_missing_entirely() -> None:
    """The editor dropped the WHOLE `bb` section from its output. There is
    nothing to reconcile metrics into, but the protected corridor going
    missing must still hard-fail — not silently pass because the section
    itself vanished."""
    raw_sections = [_bb_raw_section()]
    final_brief = _make_brief_payload([_make_section_v6("fx")])  # bb absent

    with pytest.raises(MetricReconciliationError) as exc_info:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    assert "bb.bb_policy_rate" in str(exc_info.value)
    assert "bb.bb_sdf" in str(exc_info.value)
    assert "bb.bb_slf" in str(exc_info.value)


# ─── 5. Normal pass-through unchanged ───────────────────────────────────


def test_reconcile_pass_through_when_editor_kept_everything() -> None:
    """The editor kept all metrics of a section, none invented, all labels
    matched — reconciliation must leave the metrics list byte-for-byte
    equivalent (same labels, same values, same order, no exception)."""
    healthy_bb_raw, healthy_bb_final = _healthy_bb_pair()
    raw_sections = [
        healthy_bb_raw,
        {
            "slug": "fx",
            "metrics": [
                _raw_metric("fx_bdt_usd", "BDT/USD", 123.5, unit="BDT"),
                _raw_metric("fx_gold", "Gold", 2450.0, unit="USD/oz"),
            ],
        },
    ]
    original_metrics = [
        MetricV6(label="BDT/USD", value="123.50 BDT"),
        MetricV6(label="Gold", value="2,450.00 USD/oz"),
    ]
    fx_stored = _make_section_v6("fx", metrics=list(original_metrics))
    final_brief = _make_brief_payload([healthy_bb_final, fx_stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    fx_section = next(s for s in final_brief.sections if s.slug == "fx")
    result = fx_section.metrics
    assert len(result) == 2
    assert [m.label for m in result] == ["BDT/USD", "Gold"]
    assert [m.value for m in result] == ["123.50 BDT", "2,450.00 USD/oz"]


def test_reconcile_no_op_when_slug_has_no_raw_counterpart() -> None:
    """A final_brief section with no matching slug in raw_sections (should
    never happen given _to_v6_raw is the only producer) is left untouched —
    defensive, mirrors _stamp_freshness's same guard."""
    healthy_bb_raw, healthy_bb_final = _healthy_bb_pair()
    raw_sections = [healthy_bb_raw]  # no "ghost" entry
    ghost_section = _make_section_v6("ghost", metrics=[MetricV6(label="Mystery", value="1")])
    final_brief = _make_brief_payload([healthy_bb_final, ghost_section])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    ghost = next(s for s in final_brief.sections if s.slug == "ghost")
    assert [m.label for m in ghost.metrics] == ["Mystery"]


# ─── 6. Integration: real bb.py builder output ──────────────────────────


def test_reconcile_against_real_bb_builder_output() -> None:
    """End-to-end against brief.builders.bb.build()'s actual output, not a
    hand-built fixture — proves the fix against the shape production code
    emits. Simulates the editor dropping SDF, matching issue 186's actual
    casualty (SDF + Gross Reserves; Gross Reserves is intentionally not in
    the protected set, so only SDF's survival is asserted here)."""
    from unittest.mock import MagicMock

    from brief.builders import BuilderContext
    from brief.builders.bb import build as bb_build
    from brief.econdelta import EconDeltaSnapshot
    from brief.history import HistoryRow

    today = date(2026, 8, 5)
    snapshot = EconDeltaSnapshot(
        updated_at=datetime(2026, 8, 5, tzinfo=timezone.utc),
        sources_status={},
        data={"gross_reserves_usd_bn": 25.5, "reserves_date": "2026-08-05"},
    )
    history = MagicMock()
    live_rows = {
        "policy_rate_repo": HistoryRow("policy_rate_repo", today, 9.50, "BB"),
        "policy_rate_sdf": HistoryRow("policy_rate_sdf", today, 7.50, "BB"),
        "policy_rate_slf": HistoryRow("policy_rate_slf", today, 11.00, "BB"),
        "call_money_rate": HistoryRow("call_money_rate", today, 9.48, "BB"),
    }
    history.get_latest.side_effect = lambda metric_id, table="metric_history": live_rows.get(metric_id)

    ctx = BuilderContext(snapshot=snapshot, history=history, today=today)
    section_data = bb_build(ctx)

    raw_sections = pipeline_v6._to_v6_raw([section_data], today=today)
    raw_bb = next(s for s in raw_sections if s["slug"] == "bb")
    built_ids = {m["id"] for m in raw_bb["metrics"]}
    assert {"bb_policy_rate", "bb_sdf", "bb_slf"} <= built_ids

    # Simulate the editor storing everything the builder built EXCEPT SDF
    # (mirroring editor_v6's discretionary drop).
    survivors = [
        MetricV6(
            label=m["label"],
            value=f"{m['value']:.2f}{m['unit']}" if m["unit"] == "%" else str(m["value"]),
        )
        for m in raw_bb["metrics"]
        if m["id"] != "bb_sdf"
    ]
    stored = _make_section_v6("bb", metrics=survivors)
    final_brief = _make_brief_payload([stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    bb_section = final_brief.sections[0]
    labels = {m.label for m in bb_section.metrics}
    assert "SDF" in labels
    sdf = next(m for m in bb_section.metrics if m.label == "SDF")
    assert sdf.value == "7.50%"
    # Policy Rate and SLF were never dropped by this simulated editor —
    # confirms reconciliation didn't disturb metrics that already survived.
    assert "Policy Rate" in labels
    assert "SLF" in labels
