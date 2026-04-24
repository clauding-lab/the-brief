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


from dataclasses import dataclass as _dc
from datetime import datetime, timezone

from brief.builders import SPINE_BUILDER_IDS
from brief.claude.max_client import MaxCallError, MaxCallResult, run_max
from brief.claude.validators import (
    ValidationResult,
    validate_curation,
    validate_insights,
    validate_signals,
)
from brief.claude.validators import validate_risk_map_layout, validate_todays_call
from brief.schema import BankerReadFreeform, BankerReadInsight, BankerReadStructured, MapCoord, TodaysCall


def _load_prompt(name: str) -> str:
    from pathlib import Path
    p = Path(__file__).parent / "claude" / "prompts" / name
    return p.read_text(encoding="utf-8")


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
    for s in sections_v2:
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
        v = validate_risk_map_layout(
            r.parsed,
            section_ids={s.id for s in sections_v2},
            known_metric_ids={s.id: {m.id for m in s.metrics} for s in sections_v2},
        )
        if v.ok:
            return (v.value["sections"], v.value["read_order"])
        return None
    except MaxCallError:
        return None


def call_todays_call(
    sections_v2: list,
    claude_outputs: dict,
    risk_map_sections: list[MapCoord],
    read_order: list[str],
    *,
    run_max_fn=None,
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
        if v.ok:
            return v.value
        return None
    except MaxCallError:
        return None


def _fallback_risk_map_layout(sections_v2: list) -> tuple[list[MapCoord], list[str]]:
    """Pure, deterministic. Same input → same output."""
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
    if not read_order:
        return TodaysCall(text="No single call today — see Flow Index for the full read.")

    by_id = {s.id: s for s in sections_v2}
    lead = by_id.get(read_order[0])

    if lead is None:
        return TodaysCall(text="No single call today — see Flow Index for the full read.")

    if lead.bankerread is not None:
        br = lead.bankerread
        if br.kind == "structured":
            return TodaysCall(text=br.pull)
        # freeform
        if br.pull:
            return TodaysCall(text=br.pull)
        return TodaysCall(text=br.text[:400])

    return TodaysCall(text="No single call today — see Flow Index for the full read.")


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
        call_reports.append({"name": "headlines_curation", "status": "ok" if v.ok else "invalid", "reason": v.reason})
    except MaxCallError as e:
        call_reports.append({"name": "headlines_curation", "status": "error", "reason": str(e)})

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
        call_reports.append({"name": "exec_signals", "status": "ok" if v.ok else "invalid", "reason": v.reason})
    except MaxCallError as e:
        call_reports.append({"name": "exec_signals", "status": "error", "reason": str(e)})

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
                                 "reason": v.reason, "dropped": v.dropped})
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
                                 "reason": v.reason, "dropped": v.dropped})
    except MaxCallError as e:
        call_reports.append({"name": "bankerread", "status": "error", "reason": str(e)})

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

from brief.render.assemble import assemble_brief


@_dc
class RunResult:
    sections: list
    html: str
    claude_outputs: dict
    call_reports: list[dict]
    map_coords: list[MapCoord] = field(default_factory=list)
    todays_call: TodaysCall | None = None
    read_order: list[str] = field(default_factory=list)


def run(
    cfg: PipelineConfig,
    *,
    shell_path: _Path | str,
    snapshot_override: EconDeltaSnapshot | None = None,
) -> RunResult:
    pr = run_pipeline(cfg, snapshot_override=snapshot_override)

    risk_map_result = call_risk_map_layout(pr.sections, pr.claude_outputs, cfg.today.isoformat())
    if risk_map_result is None:
        map_coords, read_order = _fallback_risk_map_layout(pr.sections)
    else:
        map_coords, read_order = risk_map_result

    todays_call = call_todays_call(pr.sections, pr.claude_outputs, map_coords, read_order)
    if todays_call is None:
        todays_call = _fallback_todays_call(read_order, pr.sections)

    html = assemble_brief(shell_path, pr.sections)
    return RunResult(
        sections=pr.sections,
        html=html,
        claude_outputs=pr.claude_outputs,
        call_reports=pr.call_reports,
        map_coords=map_coords,
        todays_call=todays_call,
        read_order=read_order,
    )
