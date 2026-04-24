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
    html = assemble_brief(shell_path, pr.sections)
    return RunResult(
        sections=pr.sections,
        html=html,
        claude_outputs=pr.claude_outputs,
        call_reports=pr.call_reports,
    )
