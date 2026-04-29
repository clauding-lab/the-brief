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
from dataclasses import dataclass as _dc
from datetime import datetime, timezone
from pathlib import Path

from brief.builders import SPINE_BUILDER_IDS
from brief.claude.max_client import MaxCallError, run_max
from brief.claude.validators import (
    validate_curation,
    validate_insights,
    validate_signals,
)
from brief.claude.validators import validate_risk_map_layout, validate_todays_call
from brief.schema import (
    BankerReadFreeform,
    BankerReadStructured,
    MapCoord,
    TodaysCall,
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
    """Run the full pipeline and render HTML + email digest.

    Dispatches on BRIEF_RENDERER env var: 'v5' takes the V5 magazine path
    (render_index_html → assemble_v5 + V5 editorial calls + QA gate);
    anything else (default 'v4') takes the legacy V4 path.

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
    if renderer_mode() == "v5":
        return _run_v5(cfg, snapshot_override=snapshot_override)

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
# Renderer dispatch — render_index_html
# ─────────────────────────────────────────────────────────────────────────────


def _v4_render_section_stub(section: SectionData) -> str:
    """V4 fallback for sections without V5 templates yet.

    Returns a minimal V4-compatible section HTML stub.
    The full V4 renderer is in brief/render/v4/; for the pilot we only need
    a placeholder that doesn't break the page.
    """
    return (
        f'<section id="section-{section.id}" class="section-v4-stub">'
        f"<h2>{section.title}</h2>"
        f"<p>(V4 fallback — pending V5 migration)</p>"
        f"</section>"
    )


def render_index_html(
    *,
    sections: list[SectionData],
    today: date,
    today_label: str,
    live: dict,
    run_meta: dict,
    headlines_curation_result: Any,
    previous_edition: dict | None = None,
    call_reports: list[dict] | None = None,
) -> tuple[str, dict]:
    """Render the full index.html.

    Mode chosen by BRIEF_RENDERER env var (default: v4).
    Returns (html_string, render_meta_dict).

    V5 meta includes: renderer_mode, qa (EditorialQAResult serialised).
    V4 meta includes: renderer_mode only.
    When call_reports is provided in V5 mode, per-call observability entries
    are appended for run_v5_editorial and run_v5_qa_gate.
    """
    mode = renderer_mode()

    if mode == "v5":
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_bb import render_section_bb

        # Run V5 editorial calls (Calls 1, 3, 4, 5)
        top_picks, todays_call, bankerreads, systemic_risks = run_v5_editorial(
            sections=sections,
            today=today,
            headlines_curation_result=headlines_curation_result,
            previous_edition=previous_edition,
            call_reports=call_reports,
        )
        # Attach editorial outputs to sections
        for s in sections:
            s.bankerread = bankerreads.get(s.id)
            s.systemic_risk = systemic_risks.get(s.id)

        section_renderers: dict = {"bb": render_section_bb}

        html = assemble_v5(
            sections=sections,
            section_renderers=section_renderers,
            v4_renderer_fallback=_v4_render_section_stub,
            top_picks=top_picks,
            todays_call=todays_call,
            live=live,
            run_meta=run_meta,
            today_label=today_label,
        )

        # Run Call 6 QA gate
        qa_result = run_v5_qa_gate(
            sections=sections,
            todays_call=todays_call,
            top_picks=top_picks,
            rendered_html=html,
            today=today,
            call_reports=call_reports,
        )
        return html, {"qa": qa_result.model_dump(mode="json"), "renderer_mode": "v5"}

    # V4 path — unchanged
    from brief.render.v4.assemble import assemble_brief as _assemble_v4

    # Construct a minimal RunResult-like object for the V4 assembler
    _rr = RunResult(
        sections=sections,
        html="",
        claude_outputs={},
        call_reports=[],
        map_coords=[],
        todays_call=None,
        read_order=[],
        email_text="",
    )
    html = _assemble_v4(_rr)
    return html, {"renderer_mode": "v4"}


# ─────────────────────────────────────────────────────────────────────────────
# V5 re-exports — V5 pipeline lives in brief/pipeline_v5.py
# ─────────────────────────────────────────────────────────────────────────────
# Re-imported here so callers that do `from brief.pipeline import run_v5_editorial`
# (etc.) keep working without code changes. Do not delete: tests + render_index_html
# depend on these names being available on this module.
from brief.pipeline_v5 import (  # noqa: E402,F401
    _V5_KICKER_BY_ID,
    _placement_for,
    _record_v5_call_error,
    _record_v5_call_ok,
    _run_v5,
    _run_v5_headlines_curation,
    _section_n,
    _section_summary_for_qa,
    _section_summary_for_top_picks,
    _strip_css_and_script,
    _todays_call_fallback,
    _top_picks_fallback,
    _triggering_metric_for,
    _v5_apply_section_adapter,
    _v5_metric_value,
    _v5_synthesize_tldr,
    run_v5_editorial,
    run_v5_qa_gate,
)

