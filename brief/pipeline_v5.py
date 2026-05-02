"""V5 editorial pipeline — Claude-powered banker daily.

Extracted from pipeline.py during V5 Plan B (Pre-Wave) on 2026-04-29.
Pure code-move refactor: no behavior changes from extraction.

Public functions used by pipeline.run / render_index_html:
- run_v5_editorial
- run_v5_qa_gate
- _run_v5_headlines_curation
- _run_v5
- _v5_apply_section_adapter

Private helpers stay private (underscore-prefixed).
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

from brief.cadence import evaluate_risk_rules, now_bdt
from brief.claude.max_client import MaxCallError, MaxCallResult
from brief.claude.validators import (
    validate_bankerread_structured,
    validate_curation,
    validate_editorial_qa,
    validate_systemic_risk_callout,
    validate_top_picks,
)
from brief.claude.validators import validate_todays_call
from brief.econdelta import EconDeltaSnapshot
from brief.schema import (
    BankerReadInsight,
    EditorialQAResult,
    GridEntry,
    MapPoint,
    QAIssue,
    SectionData,
    SystemicRisk,
    TodaysCall,
    TopPicks,
)

# Late-binding handle for pipeline.py. Using `import brief.pipeline as _pipeline`
# rather than `from brief.pipeline import X` achieves two things:
# 1. Breaks the circular-import at module-load time (pipeline.py re-imports
#    from pipeline_v5 at its bottom; if pipeline_v5 also did a `from`-import
#    of specific names at load time, Python's import machinery would resolve the
#    cycle but the bound names in pipeline_v5's namespace would point to the
#    original function objects — not the patched ones during test runs).
# 2. Attribute access on `_pipeline` happens AT CALL TIME, so test patches of
#    `brief.pipeline.render_index_html` (etc.) are always picked up correctly.
import brief.pipeline as _pipeline  # noqa: E402

_log = logging.getLogger(__name__)


# V5 Editorial Pipeline — Calls 1, 3, 4, 5, 6
# ─────────────────────────────────────────────────────────────────────────────


def _record_v5_call_ok(
    call_reports: list[dict] | None,
    name: str,
    *,
    result: MaxCallResult,
    status: str,
    reason: str | None = None,
) -> None:
    """Append a V5 Claude-call entry to call_reports (no-op if None)."""
    if call_reports is None:
        return
    call_reports.append({
        "name": name,
        "status": status,
        "reason": reason,
        "cost_usd": float(result.total_cost_usd or 0.0),
        "duration_s": float(result.duration_s),
        "tokens": result.tokens,
    })


def _record_v5_call_error(
    call_reports: list[dict] | None,
    name: str,
    reason: str,
) -> None:
    """Append a V5 Claude-call error entry to call_reports (no-op if None)."""
    if call_reports is None:
        return
    call_reports.append({
        "name": name,
        "status": "error",
        "reason": reason,
        "cost_usd": 0.0,
        "duration_s": 0.0,
        "tokens": {"input": 0, "output": 0},
    })


def run_v5_editorial(
    *,
    sections: list[SectionData],
    today: date,
    headlines_curation_result,  # output of existing V4 Call 2
    previous_edition: dict | None = None,
    call_reports: list[dict] | None = None,
) -> tuple[TopPicks, TodaysCall, dict[str, BankerReadInsight | None], dict[str, SystemicRisk | None]]:
    """Run Calls 1, 3, 4, 5 against all 14 sections.

    Returns: (top_picks, todays_call, bankerreads_by_id, systemic_risks_by_id).
    Per-section failures fall back to previous edition where available; never raise.
    When call_reports is provided, each Claude call appends an observability entry.
    """
    section_by_id = {s.id: s for s in sections}
    allowed_ids = set(section_by_id.keys())

    # ---- Call 1: top_picks ----
    summaries = [_section_summary_for_top_picks(s) for s in sections]
    top_picks_input = {
        "today": today.isoformat(),
        "sections": summaries,
        "previous_front_of_book_id": (previous_edition or {}).get("front_of_book_id"),
    }
    prompt = _pipeline._fill(_pipeline._load_prompt("top_picks.txt"), {"today": today.isoformat()})
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(top_picks_input, indent=2)
    try:
        result = _pipeline.run_max(prompt=body)
        if result.parsed is not None:
            v = validate_top_picks(result.parsed, allowed_ids=allowed_ids)
            top_picks = v.value if v.ok else _top_picks_fallback(sections)
            _record_v5_call_ok(call_reports, "top_picks", result=result,
                               status="ok" if v.ok else "invalid",
                               reason=None if v.ok else v.reason)
        else:
            top_picks = _top_picks_fallback(sections)
            _record_v5_call_ok(call_reports, "top_picks", result=result,
                               status="invalid", reason="result.parsed is None")
    except Exception as e:
        top_picks = _top_picks_fallback(sections)
        _record_v5_call_error(call_reports, "top_picks", str(e))

    # ---- Call 3: todays_call ----
    plotted_sections = [section_by_id[p.id] for p in top_picks.plotted if p.id in section_by_id]
    tc_input = {
        "today": today.isoformat(),
        "top_7_plotted": [_section_summary_for_top_picks(s) for s in plotted_sections],
        "headlines": headlines_curation_result,
        "previous_call": (previous_edition or {}).get("todays_call_text"),
    }
    prompt = _pipeline._fill(_pipeline._load_prompt("todays_call.txt"), {"today": today.isoformat()})
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(tc_input, indent=2)
    try:
        result = _pipeline.run_max(prompt=body)
        if result.parsed is not None:
            v = validate_todays_call(result.parsed)
            todays_call = v.value if v.ok else _todays_call_fallback(previous_edition)
            _record_v5_call_ok(call_reports, "todays_call", result=result,
                               status="ok" if v.ok else "invalid",
                               reason=None if v.ok else v.reason)
        else:
            todays_call = _todays_call_fallback(previous_edition)
            _record_v5_call_ok(call_reports, "todays_call", result=result,
                               status="invalid", reason="result.parsed is None")
    except Exception as e:
        todays_call = _todays_call_fallback(previous_edition)
        _record_v5_call_error(call_reports, "todays_call", str(e))

    # ---- Call 4 (×14) + Call 5 (conditional, ×N) ----
    bankerreads: dict[str, BankerReadInsight | None] = {}
    systemic_risks: dict[str, SystemicRisk | None] = {}

    def _section_call(section: SectionData) -> tuple[str, BankerReadInsight | None, SystemicRisk | None]:
        # Risk rule eval (deterministic)
        risk_active, level, rule_id = evaluate_risk_rules(section)
        section.risk_active = risk_active

        # Call 4
        is_full = section.freshness == "fresh"
        prompt_file = "bankerread_structured.txt" if is_full else "bankerread_stale_v5.txt"
        section_n = _section_n(section.id)
        try:
            prompt = _pipeline._fill(_pipeline._load_prompt(prompt_file), {
                "section_n": section_n,
                "kicker": section.kicker or "",
                "today": today.isoformat(),
            })
            br_input = {
                "section": section.model_dump(mode="json"),
                "top_picks_placement": _placement_for(section.id, top_picks),
                "previous_bankerread": (previous_edition or {}).get("bankerreads", {}).get(section.id),
            }
            body = prompt + "\n\nINPUT JSON:\n" + json.dumps(br_input, indent=2)
            result = _pipeline.run_max(prompt=body)
            br: BankerReadInsight | None = None
            if result.parsed is not None:
                v = validate_bankerread_structured(result.parsed)
                if v.ok:
                    br = v.value
                _record_v5_call_ok(call_reports, f"bankerread:{section.id}", result=result,
                                   status="ok" if v.ok else "invalid",
                                   reason=None if v.ok else v.reason)
            else:
                _record_v5_call_ok(call_reports, f"bankerread:{section.id}", result=result,
                                   status="invalid", reason="result.parsed is None")
        except Exception as e:
            br = None
            _record_v5_call_error(call_reports, f"bankerread:{section.id}", str(e))

        if br is None:
            br = (previous_edition or {}).get("bankerreads", {}).get(section.id)  # carry-over

        # Call 5 (conditional)
        sr: SystemicRisk | None = None
        if risk_active and rule_id and level:
            triggering_metric = _triggering_metric_for(section, rule_id)
            try:
                sr_prompt = _pipeline._fill(_pipeline._load_prompt("systemic_risk_callout.txt"), {
                    "section_n": section_n,
                    "kicker": section.kicker or "",
                    "today": today.isoformat(),
                    "rule_id": rule_id,
                    "level": level,
                })
                sr_input = {"section": section.model_dump(mode="json"), "triggering_metric": triggering_metric}
                sr_body = sr_prompt + "\n\nINPUT JSON:\n" + json.dumps(sr_input, indent=2)
                sr_result = _pipeline.run_max(prompt=sr_body)
                if sr_result.parsed is not None:
                    v = validate_systemic_risk_callout(sr_result.parsed, expected_level=level, rule_id=rule_id)
                    if v.ok:
                        sr = v.value
                    _record_v5_call_ok(call_reports, f"systemic_risk:{section.id}", result=sr_result,
                                       status="ok" if v.ok else "invalid",
                                       reason=None if v.ok else v.reason)
                else:
                    _record_v5_call_ok(call_reports, f"systemic_risk:{section.id}", result=sr_result,
                                       status="invalid", reason="result.parsed is None")
            except Exception as e:
                sr = None
                _record_v5_call_error(call_reports, f"systemic_risk:{section.id}", str(e))

        return (section.id, br, sr)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_section_call, s) for s in sections]
        for fut in as_completed(futures):
            try:
                sid, br, sr = fut.result()
                bankerreads[sid] = br
                systemic_risks[sid] = sr
            except Exception as exc:
                _log.warning("V5 section call failed: %s", exc)

    return top_picks, todays_call, bankerreads, systemic_risks


def run_v5_qa_gate(
    *,
    sections: list[SectionData],
    todays_call: TodaysCall,
    top_picks: TopPicks,
    rendered_html: str,
    today: date,
    call_reports: list[dict] | None = None,
) -> EditorialQAResult:
    """Call 6 — pre-flight QA. Returns a result that may block the ship.
    When call_reports is provided, the editorial_qa entry is appended."""
    # Strip CSS/script from rendered HTML to fit token budget
    excerpt = _strip_css_and_script(rendered_html)[:24000]  # rough char cap
    qa_input = {
        "today": today.isoformat(),
        "sections": [_section_summary_for_qa(s) for s in sections],
        "front_of_book": {"id": top_picks.front_of_book_id},
        "todays_call": todays_call.text,
        "rendered_html_excerpt": excerpt,
    }
    prompt = _pipeline._fill(_pipeline._load_prompt("editorial_qa.txt"), {"today": today.isoformat()})
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(qa_input, indent=2)
    try:
        result = _pipeline.run_max(prompt=body)
    except Exception as e:
        _record_v5_call_error(call_reports, "editorial_qa", str(e))
        # Never block on QA infrastructure failure
        return EditorialQAResult(
            status="pass",
            issues=[QAIssue(section_id=None, severity="warn", message="QA call raised exception; defaulted to ship")],
            shippable=True,
        )
    if result.parsed is None:
        _record_v5_call_ok(call_reports, "editorial_qa", result=result,
                           status="invalid", reason="result.parsed is None")
        return EditorialQAResult(
            status="pass",
            issues=[QAIssue(section_id=None, severity="warn", message="QA call returned no parsed output; defaulted to ship")],
            shippable=True,
        )
    v = validate_editorial_qa(result.parsed)
    _record_v5_call_ok(call_reports, "editorial_qa", result=result,
                       status="ok" if v.ok else "invalid",
                       reason=None if v.ok else v.reason)
    if not v.ok:
        return EditorialQAResult(
            status="pass",
            issues=[QAIssue(section_id=None, severity="warn", message=f"QA validator rejected output: {v.reason}; defaulted to ship")],
            shippable=True,
        )
    return v.value


# ─────────────────────────────────────────────────────────────────────────────
# V5 Private Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _section_summary_for_top_picks(s: SectionData) -> dict:
    primary = s.metrics[0] if s.metrics else None
    risk_active, _, _ = evaluate_risk_rules(s)
    return {
        "id": s.id,
        "kicker": s.kicker,
        "freshness": s.freshness,
        "key_metric": (
            {
                "label": primary.label,
                "value": primary.value,
                "delta_pct": (primary.delta.value if primary.delta else None),
                "direction": (primary.delta.direction if primary.delta else "flat"),
            }
            if primary
            else None
        ),
        "news_count": len(s.news),
        "has_systemic_risk": risk_active,
    }


def _section_summary_for_qa(s: SectionData) -> dict:
    return {
        "id": s.id,
        "kicker": s.kicker,
        "title": s.title,
        "freshness": s.freshness,
        "metric_count": len(s.metrics),
        "first_metric_as_of": (s.metrics[0].as_of.isoformat() if s.metrics else None),
        "has_bankerread": s.bankerread is not None,
        "has_systemic_risk": s.systemic_risk is not None,
        "risk_active": s.risk_active,
    }


def _section_n(section_id: str) -> str:
    """Map section id → display number."""
    mapping = {
        "headlines": "01", "bb": "02", "macro": "03", "fx": "04",
        "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
        "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
        "dam": "13", "exec": "14",
    }
    return mapping.get(section_id, "??")


# Editorial kickers shown in V5 section headers, top-of-book pull-quotes,
# risk-map labels, and grid cards. V4 builders predate the kicker field, so
# the adapter below fills these in if the builder left kicker empty.
_V5_KICKER_BY_ID: dict[str, str] = {
    "headlines": "HEADLINES",
    "bb":        "POLICY & RATES",
    "macro":     "MACRO",
    "fx":        "FX & RESERVES",
    "remit":     "REMITTANCES",
    "dse":       "EQUITIES",
    "tbond":     "TREASURY",
    "iranwar":   "IRAN WAR & OIL",
    "banking":   "BANKING",
    "comm":      "COMMODITIES",
    "fiscal":    "FISCAL",
    "nbr":       "TAX & CUSTOMS",
    "dam":       "FOOD PRICES",
    "exec":      "EXEC SIGNALS",
}


def _v5_synthesize_tldr(s: SectionData) -> str:
    """Build a one-line tldr from the section's primary metric.
    Falls back to a freshness-aware message when no metric is available."""
    if s.metrics:
        m = s.metrics[0]
        delta = ""
        if m.delta is not None:
            sign = "+" if m.delta.value >= 0 else ""
            delta = f" ({sign}{m.delta.value:.2f}%)"
        unit = f" {m.unit}" if m.unit else ""
        return f"{m.label}: {m.value}{unit}{delta}"
    if s.freshness == "fresh":
        return s.title
    return f"{s.title} — awaiting fresh data"


def _v5_apply_section_adapter(sections: list[SectionData]) -> None:
    """Fill in V5 section header fields (kicker, tldr) where V4 builders
    leave them empty. Mutates sections in place. No-op for fields already set."""
    for s in sections:
        if not s.kicker:
            s.kicker = _V5_KICKER_BY_ID.get(s.id, s.title.upper())
        if not s.tldr:
            s.tldr = _v5_synthesize_tldr(s)


def _placement_for(section_id: str, picks: TopPicks) -> dict:
    plotted = any(p.id == section_id for p in picks.plotted)
    grid = any(g.id == section_id for g in picks.grid)
    fob = (section_id == picks.front_of_book_id)
    return {"plotted": plotted, "front_of_book": fob, "grid": grid}


def _triggering_metric_for(section: SectionData, rule_id: str) -> dict | None:
    metric_id_map = {
        "banking_npl_above_30": "banking_npl_pct",
        "banking_npl_above_20": "banking_npl_pct",
        "fx_reserves_below_32bn": "bb_gross_reserves",
        "fx_reserves_below_34bn": "bb_gross_reserves",
        "fx_usd_bdt_above_124": "fx_usd_bdt",
    }
    target = metric_id_map.get(rule_id)
    if not target:
        return None
    m = next((m for m in section.metrics if m.id == target), None)
    if m is None:
        return None
    return {"id": m.id, "label": m.label, "value": m.value, "unit": m.unit, "as_of": m.as_of.isoformat()}


def _top_picks_fallback(sections: list[SectionData]) -> TopPicks:
    """Deterministic fallback when Call 1 fails: rank by |delta_pct| × freshness_weight."""
    fw = {"fresh": 1.0, "warn": 0.8, "stale": 0.6, "warming_up": 0.5, "pending": 0.4, "unavailable": 0.0}

    def score(s: SectionData) -> float:
        primary = s.metrics[0] if s.metrics else None
        delta = abs(primary.delta.value) if (primary and primary.delta) else 0
        return delta * fw.get(s.freshness, 0.5) + (5 if any(evaluate_risk_rules(s)[:1]) else 0)

    ranked = sorted(sections, key=score, reverse=True)
    plotted = [MapPoint(id=s.id, x=5.0, y=5.0, r=24, kind="fresh") for s in ranked[:7]]
    grid = [GridEntry(id=s.id, tldr=s.tldr or s.kicker) for s in ranked[7:14]]
    return TopPicks(plotted=plotted, grid=grid, front_of_book_id=ranked[0].id)


def _todays_call_fallback(previous_edition: dict | None) -> TodaysCall:
    text = (previous_edition or {}).get("todays_call_text") or "Today's call carried over from previous edition."
    return TodaysCall(text=text + " (carried over)", generated_at=datetime.now(timezone.utc))


def _strip_css_and_script(html: str) -> str:
    import re
    s = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.DOTALL)
    return s


# ─────────────────────────────────────────────────────────────────────────────
# V5 pipeline.run() entrypoint
# ─────────────────────────────────────────────────────────────────────────────


def _run_v5_headlines_curation(
    sections: list[SectionData],
) -> tuple[dict | None, list[dict]]:
    """Run V4 headlines_curation Call (still used by V5 to feed render_index_html).

    Returns (curation_result_or_None, [call_report_entry]).
    Never raises; on failure, returns (None, [error_report]).
    """
    import json as _json

    by_id = {s.id: s for s in sections}
    headlines_section = by_id.get("headlines")
    raw_headlines = list(headlines_section.news) if headlines_section else []
    allowed_urls = {h.url for h in raw_headlines}

    try:
        prompt = _pipeline._fill(_pipeline._load_prompt("headlines_curation.txt"), {
            "HEADLINES_JSON": _json.dumps(
                [{"title": h.title, "url": h.url, "source": h.source,
                  "published": h.published.isoformat()} for h in raw_headlines]
            ),
        })
        r = _pipeline.run_max(prompt=prompt, timeout_s=600)
        v = validate_curation(r.parsed, allowed_urls=allowed_urls)
        result = v.value if v.ok else None
        report = {
            "name": "headlines_curation",
            "status": "ok" if v.ok else "invalid",
            "reason": v.reason,
            "cost_usd": float(r.total_cost_usd or 0.0),
            "duration_s": float(r.duration_s),
            "tokens": r.tokens,
        }
        return result, [report]
    except MaxCallError as e:
        return None, [{
            "name": "headlines_curation",
            "status": "error",
            "reason": str(e),
            "cost_usd": 0.0,
            "duration_s": 0.0,
            "tokens": {"input": 0, "output": 0},
        }]


def _v5_metric_value(section: SectionData | None, metric_id: str) -> Any:
    if section is None:
        return None
    for m in section.metrics:
        if m.id == metric_id:
            return m.value
    return None


def _run_v5(
    cfg: _pipeline.PipelineConfig,
    *,
    snapshot_override: EconDeltaSnapshot | None = None,
) -> _pipeline.RunResult:
    """V5 pipeline path — gather → headlines_curation → render_index_html.

    Internally fires V5 Calls 1, 3, 4, 5, 6 via render_index_html() →
    run_v5_editorial() + run_v5_qa_gate(). Returns a RunResult shaped for
    the CLI/run_report consumers; email_text is empty (V5 has no email yet).
    """
    sections = _pipeline.gather(cfg, snapshot_override=snapshot_override)
    _v5_apply_section_adapter(sections)
    by_id = {s.id: s for s in sections}

    call_reports: list[dict] = []
    headlines_curation_result, headline_reports = _pipeline._run_v5_headlines_curation(sections)
    call_reports.extend(headline_reports)

    live = {
        "usd_bdt": _v5_metric_value(by_id.get("fx"), "fx_usd_bdt_mid"),
        "dsex": _v5_metric_value(by_id.get("dse"), "dse_dsex_close"),
        "brent_usd": _v5_metric_value(by_id.get("iranwar"), "iranwar_brent_spot"),
        "reserves_bn_usd": _v5_metric_value(by_id.get("bb"), "bb_gross_reserves"),
        "generated_at": now_bdt(),
        "next_update_label": "18:00 BDT CLOSE",
    }

    today_label = cfg.today.strftime("%a %d %b %Y")
    sources_used = sorted({m.source for s in sections for m in s.metrics if m.source})
    issue_no = (cfg.today - date(2026, 1, 1)).days + 1

    run_meta = {
        "vol": "II",
        "issue": issue_no,
        "sources_used": sources_used,
        "render_duration_s": 0,
        "total_cost_usd": 0.0,
    }

    html, render_meta = _pipeline.render_index_html(
        sections=sections,
        today=cfg.today,
        today_label=today_label,
        live=live,
        run_meta=run_meta,
        headlines_curation_result=headlines_curation_result,
        previous_edition=None,
        call_reports=call_reports,
    )

    claude_outputs: dict[str, Any] = {"v5_render_meta": render_meta}
    if headlines_curation_result is not None:
        claude_outputs["headlines_curation"] = headlines_curation_result

    return _pipeline.RunResult(
        sections=sections,
        html=html,
        claude_outputs=claude_outputs,
        call_reports=call_reports,
        map_coords=[],
        todays_call=None,
        read_order=[],
        email_text="",
    )
