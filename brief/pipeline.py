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
    """Subset of sections eligible for the Risk Map (excludes exec + headlines)."""
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

    _enrich_metric_history(sections, history, today=cfg.today)
    return sections


def _enrich_metric_history(
    sections: list[SectionData],
    history: Optional[MetricHistoryClient],
    *,
    today: date,
    days: int = 14,
) -> None:
    """Best-effort: pull last-N readings for every metric and attach to
    `Metric.history_values`. Powers V5 sparklines and the yield-curve hero.

    No-ops when history is unavailable; sparkline render handles missing
    history by emitting nothing.
    """
    if history is None:
        return
    all_ids = list({m.id for s in sections for m in s.metrics})
    if not all_ids:
        return
    try:
        history_map = history.get_history_window(all_ids, days=days, today=today)
    except Exception as e:  # network / parse — render must not fail
        _log.warning("history window fetch failed: %s: %s", type(e).__name__, e)
        return
    for s in sections:
        for m in s.metrics:
            vals = history_map.get(m.id)
            if vals:
                m.history_values = vals


from dataclasses import dataclass as _dc
from pathlib import Path as _Path

from brief.schema import MapCoord, TodaysCall

PROMPTS_DIR = _Path(__file__).parent / "claude" / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


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
