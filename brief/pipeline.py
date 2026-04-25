"""Pipeline orchestrator — Phase 2 version (no Claude wiring yet).

Phase 3 will extend gather() with 3 Claude calls; Phase 4 adds render().
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

_log = logging.getLogger(__name__)

from brief.builders import ALL_BUILDER_IDS, BuilderContext
from brief.cadence import now_bdt
from brief.econdelta import EconDeltaSnapshot, load_snapshot, EconDeltaUnavailable
from brief.headlines import scrape_all
from brief.history import MetricHistoryClient
from brief.schema import SectionData

_RISK_MAP_EXCLUDED: frozenset[str] = frozenset({"exec", "headlines"})


def _risk_map_sections(sections: list) -> list:
    """Subset of sections eligible for the Risk Map (12 of 14 builders)."""
    return [s for s in sections if s.id not in _RISK_MAP_EXCLUDED]


@dataclass
class PipelineConfig:
    today: date = field(default_factory=lambda: now_bdt().date())
    enable_history: bool = True
    enable_headlines: bool = True
    econdelta_path: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_key: Optional[str] = None
    claude_outputs: dict[str, Any] = field(default_factory=dict)


def _build_history(cfg: PipelineConfig) -> Optional[MetricHistoryClient]:
    if not cfg.enable_history:
        return None
    url = cfg.supabase_url or os.environ.get("SUPABASE_URL")
    key = (
        cfg.supabase_key
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY")
    )
    if not url or not key:
        return None
    return MetricHistoryClient(url=url, service_key=key)


def gather(
    cfg: PipelineConfig,
    *,
    snapshot_override: Optional[EconDeltaSnapshot] = None,
) -> list[SectionData]:
    snapshot = snapshot_override
    if snapshot is None:
        try:
            path = cfg.econdelta_path or os.environ.get("ECONDELTA_DATA") or "/home/adnan/econdelta/data/latest.json"
            snapshot = load_snapshot(path)
        except EconDeltaUnavailable:
            snapshot = EconDeltaSnapshot(
                updated_at=now_bdt(), sources_status={}, data={},
            )

    history = _build_history(cfg)
    headlines = scrape_all() if cfg.enable_headlines else []

    ctx = BuilderContext(
        snapshot=snapshot,
        history=history,
        today=cfg.today,
        headlines=tuple(headlines),
        claude_outputs=cfg.claude_outputs,
    )

    sections: list[SectionData] = []
    for bid in ALL_BUILDER_IDS:
        try:
            mod = importlib.import_module(f"brief.builders.{bid}")
            sections.append(mod.build(ctx))
        except Exception as e:
            _log.warning("builder %s failed: %s: %s", bid, type(e).__name__, e)
            sections.append(SectionData(
                id=bid,
                title=bid.upper(),
                freshness="unavailable",
                freshness_reason=f"builder error: {type(e).__name__}: {e}",
            ))
    return sections


import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass as _dc
from datetime import datetime, timezone
from pathlib import Path

from brief.builders import SPINE_BUILDER_IDS
from brief.cadence import evaluate_risk_rules
from brief.claude.max_client import MaxCallError, MaxCallResult, run_max
from brief.claude.validators import (
    ValidationResult,
    validate_bankerread_structured,
    validate_curation,
    validate_editorial_qa,
    validate_insights,
    validate_signals,
    validate_systemic_risk_callout,
    validate_top_picks,
)
from brief.claude.validators import validate_risk_map_layout, validate_todays_call
from brief.schema import (
    BankerReadFreeform,
    BankerReadInsight,
    BankerReadStructured,
    EditorialQAResult,
    GridEntry,
    MapCoord,
    MapPoint,
    QAIssue,
    SystemicRisk,
    TodaysCall,
    TopPicks,
)

PROMPTS_DIR = Path(__file__).parent / "claude" / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def renderer_mode() -> str:
    """Returns 'v4' or 'v5' based on BRIEF_RENDERER env (default v4)."""
    return os.environ.get("BRIEF_RENDERER", "v4").lower()


def _fill(template: str, replacements: dict[str, str]) -> str:
    out = template
    for k, v in replacements.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def _section_to_json(s) -> dict:
    return s.model_dump(mode="json")


_Y_BASELINE: dict[str, float] = {
    "bb": 8.0, "macro": 7.0, "fx": 7.0, "remit": 6.0,
    "dse": 6.0, "tbond": 5.0, "iranwar": 7.0, "headlines": 5.0,
    "exec": 6.0, "comm": 5.0, "banking": 6.0, "dam": 4.0,
    "fiscal": 5.0, "nbr": 4.0,
}


def _build_risk_map_input(
    sections_v2: list,
    exec_signals: dict,
    bankerread_insights: dict,
    today_iso: str,
) -> dict:
    """Produce the payload shape defined by fixtures/sample_risk_map_input.json."""
    import json as _json

    section_entries = []
    for s in _risk_map_sections(sections_v2):
        # kicker: pull > freshness_reason[:140] > ""
        kicker = ""
        if s.pull:
            kicker = s.pull
        elif s.freshness_reason:
            kicker = s.freshness_reason[:140]

        # top 3 metrics by abs(delta.value); flat/None delta ranks last
        def _delta_sort_key(m):
            if m.delta is None or m.delta.direction == "flat":
                return 0.0
            return abs(m.delta.value)

        sorted_metrics = sorted(s.metrics, key=_delta_sort_key, reverse=True)
        top3 = sorted_metrics[:3]

        top_metrics_out = []
        for m in top3:
            entry = {
                "id": m.id,
                "label": m.label,
                "value": m.value,
                "unit": m.unit,
                "delta": None,
            }
            if m.delta is not None:
                entry["delta"] = {
                    "value": m.delta.value,
                    "direction": m.delta.direction,
                    "window": m.delta.window,
                }
            top_metrics_out.append(entry)

        section_entries.append({
            "section_id": s.id,
            "title": s.title,
            "kicker": kicker,
            "freshness": s.freshness,
            "top_metrics": top_metrics_out,
        })

    # Serialize bankerread_insights (dict[section_id, BankerReadStructured|Freeform])
    br_serialized: dict[str, Any] = {}
    for sid, br in bankerread_insights.items():
        if br is None:
            br_serialized[sid] = None
        elif hasattr(br, "model_dump"):
            br_serialized[sid] = br.model_dump()
        else:
            br_serialized[sid] = br

    return {
        "today_iso": today_iso,
        "sections": section_entries,
        "exec_signals": exec_signals,
        "bankerread_insights": br_serialized,
    }


def call_risk_map_layout(
    sections_v2: list,
    claude_outputs: dict,
    today_iso: str,
    *,
    run_max_fn=None,
    call_reports: list[dict] | None = None,
) -> tuple[list[MapCoord], list[str]] | None:
    """Call Claude for risk_map_layout. Returns (sections, read_order) on success, None on any failure."""
    import json as _json

    _run = run_max_fn or run_max

    # Build bankerread_insights dict from sections
    bankerread_insights = {s.id: s.bankerread for s in sections_v2 if s.bankerread is not None}
    exec_signals = claude_outputs.get("exec_signals", {})

    try:
        payload = _build_risk_map_input(sections_v2, exec_signals, bankerread_insights, today_iso)
        prompt = _fill(_load_prompt("risk_map_layout.txt"), {
            "INPUT_JSON": _json.dumps(payload, default=str),
        })
        r = _run(prompt=prompt, timeout_s=45)
        _rm_sections = _risk_map_sections(sections_v2)
        v = validate_risk_map_layout(
            r.parsed,
            section_ids={s.id for s in _rm_sections},
            known_metric_ids={s.id: {m.id for m in s.metrics} for s in _rm_sections},
        )
        if call_reports is not None:
            call_reports.append({"name": "risk_map_layout",
                                 "status": "ok" if v.ok else "invalid", "reason": v.reason,
                                 "cost_usd": float(r.total_cost_usd or 0.0), "duration_s": float(r.duration_s), "tokens": r.tokens})
        if v.ok:
            return (v.value["sections"], v.value["read_order"])
        return None
    except MaxCallError as e:
        if call_reports is not None:
            call_reports.append({"name": "risk_map_layout", "status": "error", "reason": str(e),
                                 "cost_usd": 0.0, "duration_s": 0.0, "tokens": {"input": 0, "output": 0}})
        return None


def call_todays_call(
    sections_v2: list,
    claude_outputs: dict,
    risk_map_sections: list[MapCoord],
    read_order: list[str],
    *,
    run_max_fn=None,
    call_reports: list[dict] | None = None,
) -> TodaysCall | None:
    """Call Claude for todays_call. Returns TodaysCall on success, None on any failure."""
    import json as _json

    _run = run_max_fn or run_max

    try:
        prompt = _fill(_load_prompt("todays_call.txt"), {
            "RISK_MAP_JSON": _json.dumps(
                {"sections": [mc.model_dump() for mc in risk_map_sections], "read_order": read_order},
                default=str,
            ),
            "BANKERREAD_JSON": _json.dumps(
                {s.id: (s.bankerread.model_dump() if s.bankerread else None) for s in sections_v2},
                default=str,
            ),
            "EXEC_SIGNALS_JSON": _json.dumps(claude_outputs.get("exec_signals", {}), default=str),
        })
        r = _run(prompt=prompt, timeout_s=45)
        v = validate_todays_call(r.parsed)
        if call_reports is not None:
            call_reports.append({"name": "todays_call",
                                 "status": "ok" if v.ok else "invalid", "reason": v.reason,
                                 "cost_usd": float(r.total_cost_usd or 0.0), "duration_s": float(r.duration_s), "tokens": r.tokens})
        if v.ok:
            return v.value
        return None
    except MaxCallError as e:
        if call_reports is not None:
            call_reports.append({"name": "todays_call", "status": "error", "reason": str(e),
                                 "cost_usd": 0.0, "duration_s": 0.0, "tokens": {"input": 0, "output": 0}})
        return None


def _fallback_risk_map_layout(sections_v2: list) -> tuple[list[MapCoord], list[str]]:
    """Pure, deterministic. Same input → same output."""
    sections_v2 = _risk_map_sections(sections_v2)
    map_coords: list[MapCoord] = []

    for s in sections_v2:
        # Compute x from hero/first metric with a non-flat delta
        x = 1.0
        for m in s.metrics:
            if m.delta is not None and m.delta.direction != "flat":
                raw = abs(m.delta.value) / 10.0
                x = max(0.0, min(10.0, raw))
                break

        y = _Y_BASELINE.get(s.id, 5.0)

        r = int(max(20, min(50, 20 + round((x + y) * 1.5))))

        # Determine type
        oil_events = s.extras.get("oil_events") if s.extras else None
        if oil_events and any(e.get("hotness") == "hot" for e in oil_events if isinstance(e, dict)):
            section_type: str = "event"
        elif s.id in {"bb", "macro"}:
            section_type = "anchor"
        elif s.freshness in ("fresh", "warning"):
            section_type = "fresh"
        else:
            section_type = "slow"

        coord = MapCoord(
            section_id=s.id,
            x=x,
            y=y,
            r=r,
            type=section_type,  # type: ignore[arg-type]
            hero_metric_id=None,
        )
        map_coords.append(coord)

    # read_order: sort by (x * y) descending, ties broken by ALL_BUILDER_IDS order
    coord_by_id = {mc.section_id: mc for mc in map_coords}
    ordered_ids = list(ALL_BUILDER_IDS)

    def _sort_key(sid: str):
        mc = coord_by_id[sid]
        return (-mc.x * mc.y, ordered_ids.index(sid))

    read_order = sorted(coord_by_id.keys(), key=_sort_key)

    return (map_coords, read_order)


def _fallback_todays_call(
    read_order: list[str],
    sections_v2: list,
) -> TodaysCall:
    """Deterministic. Lead section's pull → freeform.text → safe default."""
    now = datetime.now(timezone.utc)
    if not read_order:
        return TodaysCall(text="No single call today — see Flow Index for the full read.", generated_at=now)

    by_id = {s.id: s for s in sections_v2}
    lead = by_id.get(read_order[0])

    if lead is None:
        return TodaysCall(text="No single call today — see Flow Index for the full read.", generated_at=now)

    if lead.bankerread is not None:
        br = lead.bankerread
        if br.kind == "structured":
            return TodaysCall(text=br.pull, generated_at=now)
        # freeform
        if br.pull:
            return TodaysCall(text=br.pull, generated_at=now)
        return TodaysCall(text=br.text, generated_at=now)

    return TodaysCall(text="No single call today — see Flow Index for the full read.", generated_at=now)


@_dc
class PipelineResult:
    sections: list
    claude_outputs: dict
    call_reports: list[dict]


def run_pipeline(
    cfg: PipelineConfig, *, snapshot_override: EconDeltaSnapshot | None = None,
) -> PipelineResult:
    import json as _json

    # Phase A — initial gather (no Claude)
    sections_v1 = gather(cfg, snapshot_override=snapshot_override)
    by_id_v1 = {s.id: s for s in sections_v1}

    claude_outputs: dict[str, Any] = {}
    call_reports: list[dict] = []

    # Call 1 — headlines_curation
    headlines_section = by_id_v1.get("headlines")
    raw_headlines = list(headlines_section.news) if headlines_section else []
    allowed_urls = {h.url for h in raw_headlines}

    try:
        prompt = _fill(_load_prompt("headlines_curation.txt"), {
            "HEADLINES_JSON": _json.dumps(
                [{"title": h.title, "url": h.url, "source": h.source,
                  "published": h.published.isoformat()} for h in raw_headlines]
            ),
        })
        r = run_max(prompt=prompt, timeout_s=600)
        v = validate_curation(r.parsed, allowed_urls=allowed_urls)
        if v.ok:
            claude_outputs["headlines_curation"] = v.value
        call_reports.append({"name": "headlines_curation", "status": "ok" if v.ok else "invalid", "reason": v.reason,
                             "cost_usd": float(r.total_cost_usd or 0.0), "duration_s": float(r.duration_s), "tokens": r.tokens})
    except MaxCallError as e:
        call_reports.append({"name": "headlines_curation", "status": "error", "reason": str(e),
                             "cost_usd": 0.0, "duration_s": 0.0, "tokens": {"input": 0, "output": 0}})

    # Call 2 — exec_signals
    try:
        allowed_anchors = set(ALL_BUILDER_IDS)
        spine_payload = [_section_to_json(s) for s in sections_v1
                         if s.id in SPINE_BUILDER_IDS and s.freshness in ("fresh", "warning")]
        prompt = _fill(_load_prompt("exec_signals.txt"), {
            "TODAY_ISO": cfg.today.isoformat(),
            "SECTIONS_JSON": _json.dumps(spine_payload, default=str),
        })
        r = run_max(prompt=prompt, timeout_s=900)
        v = validate_signals(r.parsed, allowed_anchors=allowed_anchors)
        if v.ok:
            claude_outputs["exec_signals"] = v.value
        call_reports.append({"name": "exec_signals", "status": "ok" if v.ok else "invalid", "reason": v.reason,
                             "cost_usd": float(r.total_cost_usd or 0.0), "duration_s": float(r.duration_s), "tokens": r.tokens})
    except MaxCallError as e:
        call_reports.append({"name": "exec_signals", "status": "error", "reason": str(e),
                             "cost_usd": 0.0, "duration_s": 0.0, "tokens": {"input": 0, "output": 0}})

    # Call 3 — bankerread_insights (fresh + stale variants)
    fresh_ids = {s.id for s in sections_v1 if s.freshness in ("fresh", "warning")}
    stale_ids = {s.id for s in sections_v1 if s.freshness == "stale"}

    insights_full: dict[str, list[str]] = {}
    insights_stale: dict[str, list[str]] = {}

    try:
        if fresh_ids:
            fresh_payload = [_section_to_json(s) for s in sections_v1 if s.id in fresh_ids]
            prompt = _fill(_load_prompt("bankerread.txt"), {
                "TODAY_ISO": cfg.today.isoformat(),
                "SECTIONS_JSON": _json.dumps(fresh_payload, default=str),
                "EXEC_SIGNALS_JSON": _json.dumps(claude_outputs.get("exec_signals", {}), default=str),
            })
            r = run_max(prompt=prompt, timeout_s=1800)
            v = validate_insights(r.parsed, allowed_section_ids=fresh_ids, stale=False)
            insights_full = v.value["insights"] if v.ok else {}
            call_reports.append({"name": "bankerread_full", "status": "ok" if v.ok else "invalid",
                                 "reason": v.reason, "dropped": v.dropped,
                                 "cost_usd": float(r.total_cost_usd or 0.0), "duration_s": float(r.duration_s), "tokens": r.tokens})
        if stale_ids:
            stale_payload = {"ids": sorted(stale_ids)}
            prompt = _fill(_load_prompt("bankerread_stale.txt"), {
                "TODAY_ISO": cfg.today.isoformat(),
                "STALE_SECTIONS_JSON": _json.dumps(stale_payload),
                "HEADLINES_JSON": _json.dumps(
                    [{"title": h.title, "url": h.url} for h in raw_headlines]
                ),
            })
            r = run_max(prompt=prompt, timeout_s=900)
            v = validate_insights(r.parsed, allowed_section_ids=stale_ids, stale=True)
            insights_stale = v.value["insights"] if v.ok else {}
            call_reports.append({"name": "bankerread_stale", "status": "ok" if v.ok else "invalid",
                                 "reason": v.reason, "dropped": v.dropped,
                                 "cost_usd": float(r.total_cost_usd or 0.0), "duration_s": float(r.duration_s), "tokens": r.tokens})
    except MaxCallError as e:
        call_reports.append({"name": "bankerread", "status": "error", "reason": str(e),
                             "cost_usd": 0.0, "duration_s": 0.0, "tokens": {"input": 0, "output": 0}})

    claude_outputs["bankerread_full"] = insights_full
    claude_outputs["bankerread_stale"] = insights_stale

    # Phase B — rebuild affected sections with Claude outputs
    cfg2 = PipelineConfig(
        today=cfg.today, enable_history=cfg.enable_history,
        enable_headlines=cfg.enable_headlines,
        econdelta_path=cfg.econdelta_path,
        supabase_url=cfg.supabase_url, supabase_key=cfg.supabase_key,
        claude_outputs=claude_outputs,
    )
    sections_v2 = gather(cfg2, snapshot_override=snapshot_override)

    now = datetime.now(timezone.utc)
    for s in sections_v2:
        full_sentences = insights_full.get(s.id)
        if full_sentences and len(full_sentences) >= 4:
            s.bankerread = BankerReadStructured(
                meaning=full_sentences[0],
                action=full_sentences[1],
                trigger=full_sentences[2],
                focus=full_sentences[3],
                pull=full_sentences[0],
            )
            continue
        stale_sentences = insights_stale.get(s.id)
        if stale_sentences:
            s.bankerread = BankerReadFreeform(
                text=stale_sentences[0],
                pull=None,
            )

    return PipelineResult(
        sections=sections_v2,
        claude_outputs=claude_outputs,
        call_reports=call_reports,
    )


from pathlib import Path as _Path


@_dc
class RunResult:
    sections: list
    html: str
    claude_outputs: dict
    call_reports: list[dict]
    map_coords: list[MapCoord] = field(default_factory=list)
    todays_call: TodaysCall | None = None
    read_order: list[str] = field(default_factory=list)
    email_text: str = ""


def render_v4(run_result: "RunResult") -> tuple[str, str]:
    """Render the V4 HTML + email digest. Returns (html, email_text)."""
    from brief.render.v4.assemble import assemble_brief as assemble_v4
    from brief.render.v4.email_digest import render_email_digest
    html = assemble_v4(run_result)
    email_text = render_email_digest(run_result)
    return html, email_text


def run(
    cfg: PipelineConfig,
    *,
    shell_path: _Path | str | None = None,
    snapshot_override: EconDeltaSnapshot | None = None,
) -> RunResult:
    """Run the full pipeline and render V4 HTML + email digest.

    Parameters
    ----------
    cfg:
        Pipeline configuration.
    shell_path:
        Deprecated. Accepted for backward compatibility but no longer forwarded
        to the V4 assembler (which uses its own default shell_v4.html).
        Pass None to use V4 defaults.
    snapshot_override:
        Optional EconDeltaSnapshot to use instead of loading from disk.
    """
    pr = run_pipeline(cfg, snapshot_override=snapshot_override)

    risk_map_result = call_risk_map_layout(pr.sections, pr.claude_outputs, cfg.today.isoformat(),
                                           call_reports=pr.call_reports)
    if risk_map_result is None:
        map_coords, read_order = _fallback_risk_map_layout(pr.sections)
    else:
        map_coords, read_order = risk_map_result

    todays_call = call_todays_call(pr.sections, pr.claude_outputs, map_coords, read_order,
                                   call_reports=pr.call_reports)
    if todays_call is None:
        todays_call = _fallback_todays_call(read_order, pr.sections)

    rr = RunResult(
        sections=pr.sections,
        html="",
        claude_outputs=pr.claude_outputs,
        call_reports=pr.call_reports,
        map_coords=map_coords,
        todays_call=todays_call,
        read_order=read_order,
        email_text="",
    )
    html, email_text = render_v4(rr)
    rr.html = html
    rr.email_text = email_text
    return rr


# ─────────────────────────────────────────────────────────────────────────────
# V5 Editorial Pipeline — Calls 1, 3, 4, 5, 6
# ─────────────────────────────────────────────────────────────────────────────


def run_v5_editorial(
    *,
    sections: list[SectionData],
    today: date,
    headlines_curation_result,  # output of existing V4 Call 2
    previous_edition: dict | None = None,
) -> tuple[TopPicks, TodaysCall, dict[str, BankerReadInsight | None], dict[str, SystemicRisk | None]]:
    """Run Calls 1, 3, 4, 5 against all 14 sections.

    Returns: (top_picks, todays_call, bankerreads_by_id, systemic_risks_by_id).
    Per-section failures fall back to previous edition where available; never raise.
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
    prompt = _load_prompt("top_picks.txt").format(today=today.isoformat())
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(top_picks_input, indent=2)
    try:
        result = run_max(prompt=body, extended_thinking_budget=16000)
        if result.parsed is not None:
            v = validate_top_picks(result.parsed, allowed_ids=allowed_ids)
            top_picks = v.value if v.ok else _top_picks_fallback(sections)
        else:
            top_picks = _top_picks_fallback(sections)
    except Exception:
        top_picks = _top_picks_fallback(sections)

    # ---- Call 3: todays_call ----
    plotted_sections = [section_by_id[p.id] for p in top_picks.plotted if p.id in section_by_id]
    tc_input = {
        "today": today.isoformat(),
        "top_7_plotted": [_section_summary_for_top_picks(s) for s in plotted_sections],
        "headlines": headlines_curation_result,
        "previous_call": (previous_edition or {}).get("todays_call_text"),
    }
    prompt = _load_prompt("todays_call.txt").format(today=today.isoformat())
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(tc_input, indent=2)
    try:
        result = run_max(prompt=body, extended_thinking_budget=12000)
        if result.parsed is not None:
            v = validate_todays_call(result.parsed)
            todays_call = v.value if v.ok else _todays_call_fallback(previous_edition)
        else:
            todays_call = _todays_call_fallback(previous_edition)
    except Exception:
        todays_call = _todays_call_fallback(previous_edition)

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
            prompt = _load_prompt(prompt_file).format(
                section_n=section_n, kicker=section.kicker, today=today.isoformat()
            )
            br_input = {
                "section": section.model_dump(mode="json"),
                "top_picks_placement": _placement_for(section.id, top_picks),
                "previous_bankerread": (previous_edition or {}).get("bankerreads", {}).get(section.id),
            }
            body = prompt + "\n\nINPUT JSON:\n" + json.dumps(br_input, indent=2)
            result = run_max(prompt=body, extended_thinking_budget=12000)
            br: BankerReadInsight | None = None
            if result.parsed is not None:
                v = validate_bankerread_structured(result.parsed)
                if v.ok:
                    br = v.value
        except Exception:
            br = None

        if br is None:
            br = (previous_edition or {}).get("bankerreads", {}).get(section.id)  # carry-over

        # Call 5 (conditional)
        sr: SystemicRisk | None = None
        if risk_active and rule_id and level:
            triggering_metric = _triggering_metric_for(section, rule_id)
            try:
                sr_prompt = _load_prompt("systemic_risk_callout.txt").format(
                    section_n=section_n, kicker=section.kicker, today=today.isoformat(),
                    rule_id=rule_id, level=level,
                )
                sr_input = {"section": section.model_dump(mode="json"), "triggering_metric": triggering_metric}
                sr_body = sr_prompt + "\n\nINPUT JSON:\n" + json.dumps(sr_input, indent=2)
                sr_result = run_max(prompt=sr_body, extended_thinking_budget=8000)
                if sr_result.parsed is not None:
                    v = validate_systemic_risk_callout(sr_result.parsed, expected_level=level, rule_id=rule_id)
                    if v.ok:
                        sr = v.value
            except Exception:
                sr = None

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
) -> EditorialQAResult:
    """Call 6 — pre-flight QA. Returns a result that may block the ship."""
    # Strip CSS/script from rendered HTML to fit token budget
    excerpt = _strip_css_and_script(rendered_html)[:24000]  # rough char cap
    qa_input = {
        "today": today.isoformat(),
        "sections": [_section_summary_for_qa(s) for s in sections],
        "front_of_book": {"id": top_picks.front_of_book_id},
        "todays_call": todays_call.text,
        "rendered_html_excerpt": excerpt,
    }
    prompt = _load_prompt("editorial_qa.txt").format(today=today.isoformat())
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(qa_input, indent=2)
    try:
        result = run_max(prompt=body, extended_thinking_budget=16000)
    except Exception:
        # Never block on QA infrastructure failure
        return EditorialQAResult(
            status="pass",
            issues=[QAIssue(section_id=None, severity="warn", message="QA call raised exception; defaulted to ship")],
            shippable=True,
        )
    if result.parsed is None:
        return EditorialQAResult(
            status="pass",
            issues=[QAIssue(section_id=None, severity="warn", message="QA call returned no parsed output; defaulted to ship")],
            shippable=True,
        )
    v = validate_editorial_qa(result.parsed)
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
