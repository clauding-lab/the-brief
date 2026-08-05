"""Deterministic post-editor metric reconciliation (sdf-diagnosis-2026-08-05.md §4,
hardened per the 2026-08-05 follow-up review — findings H1/H2/M1/M2/M3/L2/L3/L4).

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
  2. Multiple missing protected metrics are re-injected AT THEIR BUILDER
     INDEX (not appended to the tail — M1), preserving the editor's ordering
     of the metrics it kept.
  3. An editor-invented label with no counterpart in the raw builder output
     is rejected (dropped) and alerted (H2), closing the "Breadth" hole.
  4. Label matching is normalized (NFC + strip + casefold) so a pure
     case/whitespace drift is NOT treated as invention (H2).
  5. A same-label duplicate within a section is deduped, keeping the first
     occurrence (L3).
  6. A protected metric relabelled by the editor is rejected then
     re-injected exactly once — no duplicate.
  7. H1 split: a protected metric the raw BUILDER never produced today
     (routine upstream blip) degrades that metric and ALERTS, but does NOT
     hard-fail the publish. A protected metric the builder DID produce, but
     that is still absent from the final brief (the editor deleted the whole
     section around it), DOES hard-fail — `MetricReconciliationError`.
  8. An editor-invented SECTION slug (no builder maps to it at all) is
     rejected from `final_brief.sections` and alerted — not silently
     published via the "no raw counterpart" skip path (L3).
  9. Normal pass-through: an editor output matching the raw builder output
     exactly is left unchanged (no drops, no re-injections, no exception).
  10. A known slug simply absent from this run's raw_sections (e.g. a
      section that legitimately didn't build) is left untouched.
  11. Integration: brief.builders.bb's own `build()` output, fed through
      `_to_v6_raw`, reconciles correctly — proves the fix against the actual
      shape production code emits, not just a hand-built fixture.

Alert assertions patch `brief.alerts.send_discord_alert` (matches
`brief.cli`'s existing pattern) — `_reconcile_metrics` never sets
DISCORD_ALERT_WEBHOOK_URL itself, so without a mock the real
`send_discord_alert` just no-ops (no webhook configured) rather than making
a network call; patching lets tests assert it was actually invoked.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import patch

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
    survived — safe "noise" for tests about a different section. Without
    it, `_verify_protected_presence` (which checks `PROTECTED_METRIC_IDS`
    unconditionally, matching production where `bb` is always in
    `sections_raw`) fires three H1 soft-alerts for a `bb` this test never
    mentions, polluting alert-count/alert-content assertions about the
    section actually under test."""
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


# ─── 1/2. Protected metric re-injection, at builder index (M1) ─────────


def test_reconcile_reinjects_editor_dropped_protected_metric() -> None:
    """SDF was in the raw builder output but the editor dropped it — the
    section carries only the 5 metrics that survived storage. Reconciliation
    must re-inject SDF, formatted as a percent to match the corridor display,
    inserted right after Policy Rate (its builder index), not appended to
    the tail (M1)."""
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

    labels = [m.label for m in final_brief.sections[0].metrics]
    assert "SDF" in labels
    sdf = next(m for m in final_brief.sections[0].metrics if m.label == "SDF")
    assert sdf.value == "7.50%"
    # M1: inserted at its builder index (1), not appended to the tail.
    assert labels[1] == "SDF"
    # Gross Reserves is NOT protected — the memo's protected set is the
    # corridor (policy/SDF/SLF) only — so it stays dropped; reconciliation
    # does not resurrect it.
    assert "Gross Reserves" not in labels


def test_reconcile_reinjects_multiple_missing_metrics_in_builder_order() -> None:
    """All three corridor metrics dropped by the editor — reconciliation
    re-injects all three, at their builder indices (M1), producing the exact
    natural corridor order ahead of the metrics the editor kept."""
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
    # M1: exact final order, not just "reinjected labels are relatively
    # ordered" — each is inserted at min(raw_index, current_length), so
    # Policy(0)->SDF(1)->SLF(2) land ahead of the two metrics the editor kept.
    assert labels == ["Policy Rate", "SDF", "SLF", "Overnight Call Money", "Gross Reserves"]


# ─── 3/4/5. Invented-label rejection, normalization, dedupe (H2, L3) ────


def test_reconcile_rejects_editor_invented_label_and_alerts() -> None:
    """The editor synthesised a "Breadth" tile with no counterpart in the
    builder's raw output (issues 177-180, §06 dse — merged from Advancing +
    Declining). Reconciliation must drop it AND alert (H2) — the deletion is
    correct, but it must never again be discoverable only via journalctl."""
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

    with patch("brief.alerts.send_discord_alert") as mock_alert:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    dse_section = next(s for s in final_brief.sections if s.slug == "dse")
    labels = {m.label for m in dse_section.metrics}
    assert labels == {"DSEX Close"}
    assert "Breadth" not in labels
    assert mock_alert.called
    breadth_calls = [c.args[0] for c in mock_alert.call_args_list if "Breadth" in c.args[0]]
    assert len(breadth_calls) == 1
    assert "dse" in breadth_calls[0]


def test_reconcile_normalization_prevents_false_deletion_on_case_and_whitespace_drift() -> None:
    """A pure case/whitespace/Unicode difference between the raw builder
    label and the editor-returned label must NOT be treated as an invented
    metric. Before normalization, "DSEX Close" (raw) vs " dsex close " or a
    full-width Unicode variant (editor) would silently empty a section to
    whatever survived — H2's stated failure mode."""
    healthy_bb_raw, healthy_bb_final = _healthy_bb_pair()
    raw_sections = [
        healthy_bb_raw,
        {
            "slug": "dse",
            "metrics": [_raw_metric("dse_dsex_close", "DSEX Close", 5230.1, unit="pts")],
        },
    ]
    dse_stored = _make_section_v6(
        "dse",
        metrics=[
            # Case-flipped + leading/trailing whitespace — same metric, drifted label.
            MetricV6(label=" dsex close ", value="5,230.10 pts"),
        ],
    )
    final_brief = _make_brief_payload([healthy_bb_final, dse_stored])

    with patch("brief.alerts.send_discord_alert") as mock_alert:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    dse_section = next(s for s in final_brief.sections if s.slug == "dse")
    # MetricV6 is `_Lenient` (str_strip_whitespace=True) so Pydantic itself
    # already stripped the surrounding whitespace at construction — the
    # remaining drift this test actually exercises _normalize_label's
    # casefold on ("dsex close" vs raw "DSEX Close"). Kept either way, not
    # rewritten to the raw casing.
    assert [m.label for m in dse_section.metrics] == ["dsex close"]
    mock_alert.assert_not_called()  # not a rejection — nothing to alert on (bb noise is healthy too)


def test_reconcile_dedupes_editor_duplicate_metric_keeping_first() -> None:
    """The editor returned the same metric twice (identical normalized
    label) — reconciliation keeps only the first occurrence."""
    raw_sections = [
        {
            "slug": "fx",
            "metrics": [_raw_metric("fx_gold", "Gold", 2450.0, unit="USD/oz")],
        },
    ]
    fx_stored = _make_section_v6(
        "fx",
        metrics=[
            MetricV6(label="Gold", value="2,450.00 USD/oz"),
            MetricV6(label="Gold", value="2,450.00 USD/oz"),  # editor duplicate
        ],
    )
    final_brief = _make_brief_payload([fx_stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    fx_section = next(s for s in final_brief.sections if s.slug == "fx")
    assert len(fx_section.metrics) == 1
    assert fx_section.metrics[0].label == "Gold"


# ─── 6. Relabelled protected metric: reject-then-reinject exactly once ──


def test_reconcile_relabelled_protected_metric_rejected_then_reinjected_once() -> None:
    """The editor kept SDF's data but returned it under a garbled/renamed
    label with no counterpart in the raw output. Reconciliation must reject
    the mislabelled entry (it matches no raw label) AND re-inject the real
    SDF from raw — ending with EXACTLY ONE "SDF" metric, not a duplicate."""
    raw_sections = [_bb_raw_section()]
    stored = _make_section_v6(
        "bb",
        metrics=[
            MetricV6(label="Policy Rate", value="9.50%"),
            MetricV6(label="Standing Deposit Facility (renamed)", value="7.50%"),  # relabelled SDF
            MetricV6(label="SLF", value="11.00%"),
            MetricV6(label="Overnight Call Money", value="9.48%"),
        ],
    )
    final_brief = _make_brief_payload([stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    bb_section = final_brief.sections[0]
    sdf_entries = [m for m in bb_section.metrics if m.label == "SDF"]
    assert len(sdf_entries) == 1
    assert sdf_entries[0].value == "7.50%"
    assert not any(m.label == "Standing Deposit Facility (renamed)" for m in bb_section.metrics)


# ─── 7. H1 split: builder-side miss degrades + alerts; editor deletion hard-fails ──


def test_reconcile_degrades_and_alerts_when_protected_metric_not_built_today() -> None:
    """The raw BUILDER itself never produced SDF/SLF today (e.g. a
    metric_history read failure inside bb.py, degrading — not crashing — the
    section per brief/pipeline.py:89-96). This is a routine upstream blip:
    reconciliation has nothing to re-inject from, so it must ALERT and let
    the publish CONTINUE — NOT hard-fail (H1). Converting a one-section blip
    into a lost morning edition would be strictly worse than today's bug."""
    raw_sections = [
        _bb_raw_section(
            metrics=[
                _raw_metric("bb_policy_rate", "Policy Rate", 9.50),
                # bb_sdf and bb_slf never built this run.
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

    with patch("brief.alerts.send_discord_alert") as mock_alert:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)  # must NOT raise

    bb_section = final_brief.sections[0]
    labels = {m.label for m in bb_section.metrics}
    assert labels == {"Policy Rate", "Overnight Call Money"}  # unchanged — nothing to reinject
    assert mock_alert.call_count == 2  # one alert each for bb_sdf, bb_slf
    alerted_ids = {c.args[0] for c in mock_alert.call_args_list}
    assert any("bb_sdf" in msg for msg in alerted_ids)
    assert any("bb_slf" in msg for msg in alerted_ids)


def test_reconcile_degraded_section_data_through_to_v6_raw_does_not_hard_fail() -> None:
    """Higher-fidelity version of the above: a real degraded `SectionData`
    (as `brief/pipeline.py:89-96` produces on a builder exception — id="bb",
    metrics=[]) fed through the actual `_to_v6_raw` adapter. Must alert and
    publish, not hard-fail (pins H1 at the real integration boundary)."""
    from brief.schema import SectionData

    degraded = SectionData(
        id="bb", title="BB", freshness="unavailable",
        freshness_reason="builder error: URLError: timed out",
    )
    raw_sections = pipeline_v6._to_v6_raw([degraded], today=date(2026, 8, 5))

    stored = _make_section_v6("bb", metrics=[])  # editor had nothing to work with either
    final_brief = _make_brief_payload([stored])

    with patch("brief.alerts.send_discord_alert") as mock_alert:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)  # must NOT raise

    assert final_brief.sections[0].metrics == []
    assert mock_alert.call_count == 3  # bb_policy_rate, bb_sdf, bb_slf all missing


def test_reconcile_hard_fails_when_section_missing_entirely() -> None:
    """The editor dropped the WHOLE `bb` section from its output, even though
    the raw builder DID produce the full corridor. There is nothing to
    re-inject into (no section to hold the metrics), and — unlike a
    builder-side miss — the data genuinely existed and the editor discarded
    it. This is the hard-fail half of H1's split."""
    raw_sections = [_bb_raw_section()]
    final_brief = _make_brief_payload([_make_section_v6("fx")])  # bb absent

    with pytest.raises(MetricReconciliationError) as exc_info:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    assert "bb.bb_policy_rate" in str(exc_info.value)
    assert "bb.bb_sdf" in str(exc_info.value)
    assert "bb.bb_slf" in str(exc_info.value)


# ─── 8. Editor-invented section slug rejected, not silently published ──


def test_reconcile_rejects_invented_section_slug_and_alerts() -> None:
    """A slug with no counterpart in ANY builder (never in V5_TO_V6) is not
    a routine "didn't build today" miss — it is a section the editor
    invented outright. The "no raw counterpart → leave alone" skip path
    must NOT let this through; it must be dropped from final_brief.sections
    and alerted (L3)."""
    raw_sections = [_bb_raw_section()]  # bb present; nothing produces "ghost"
    ghost_section = _make_section_v6("ghost", metrics=[MetricV6(label="Mystery", value="1")])
    bb_stored = _make_section_v6(
        "bb",
        metrics=[
            MetricV6(label="Policy Rate", value="9.50%"),
            MetricV6(label="SDF", value="7.50%"),
            MetricV6(label="SLF", value="11.00%"),
        ],
    )
    final_brief = _make_brief_payload([bb_stored, ghost_section])

    with patch("brief.alerts.send_discord_alert") as mock_alert:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    slugs = [s.slug for s in final_brief.sections]
    assert "ghost" not in slugs  # dropped, not silently published
    assert "bb" in slugs
    assert mock_alert.called
    assert any("ghost" in c.args[0] for c in mock_alert.call_args_list)


# ─── 9/10. Normal pass-through, known-but-absent-today slug ────────────


def test_reconcile_pass_through_when_editor_kept_everything() -> None:
    """The editor kept all metrics of a section, none invented, all labels
    matched — reconciliation must leave the metrics list byte-for-byte
    equivalent (same labels, same values, same order, no exception)."""
    raw_sections = [
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
    final_brief = _make_brief_payload([fx_stored])

    pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    fx_section = final_brief.sections[0]
    result = fx_section.metrics
    assert len(result) == 2
    assert [m.label for m in result] == ["BDT/USD", "Gold"]
    assert [m.value for m in result] == ["123.50 BDT", "2,450.00 USD/oz"]


def test_reconcile_leaves_known_slug_untouched_when_absent_from_raw_this_run() -> None:
    """`fx` is a real V6 slug (V5_TO_V6) but this run's raw_sections has no
    entry for it (e.g. a section that legitimately didn't build) — distinct
    from an INVENTED slug (test above). Left completely untouched, no alert,
    no exception — there is nothing to reconcile it against, and unlike a
    protected slug, `fx` carries no hard survival requirement."""
    healthy_bb_raw, healthy_bb_final = _healthy_bb_pair()
    raw_sections = [healthy_bb_raw]  # bb built; nothing built "fx" this run
    fx_section = _make_section_v6("fx", metrics=[MetricV6(label="Mystery", value="1")])
    final_brief = _make_brief_payload([healthy_bb_final, fx_section])

    with patch("brief.alerts.send_discord_alert") as mock_alert:
        pipeline_v6._reconcile_metrics(final_brief, raw_sections)

    fx = next(s for s in final_brief.sections if s.slug == "fx")
    assert [m.label for m in fx.metrics] == ["Mystery"]
    mock_alert.assert_not_called()  # fx is not in PROTECTED_METRIC_IDS; bb noise is healthy


# ─── 11. Integration: real bb.py builder output ─────────────────────────


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
