"""One-off debug helper: capture raw Claude Max output for failing pipeline calls.

Usage:
    python scripts/debug_call.py --call bankerread_full
    python scripts/debug_call.py --call risk_map_layout

Writes a JSON file to /tmp/brief-debug-<call_name>-<UTC_timestamp>.json
containing the full MaxCallResult (raw_text, parsed, usage, total_cost_usd).

Does NOT modify max_client.py, validators.py, or any builder.
Does NOT run validators — raw output only.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Import production code without side effects
# ---------------------------------------------------------------------------
# Add the project root to sys.path so this works from any cwd.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from brief.claude.max_client import run_max  # noqa: E402  (import after sys.path tweak)
from brief.econdelta import EconDeltaSnapshot, EconDeltaUnavailable, load_snapshot  # noqa: E402
from brief.pipeline import (  # noqa: E402
    PipelineConfig,
    _build_risk_map_input,
    _fill,
    _load_prompt,
    _risk_map_sections,
    gather,
)
from brief.cadence import now_bdt  # noqa: E402

_FIXTURES = _PROJECT_ROOT / "fixtures"
_FIXTURE_SNAPSHOT = _FIXTURES / "econdelta_latest.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture_snapshot() -> EconDeltaSnapshot:
    """Load the canonical fixture snapshot for deterministic prompt building."""
    import json as _json
    from datetime import datetime as _dt

    payload = _json.loads(_FIXTURE_SNAPSHOT.read_text(encoding="utf-8"))
    return EconDeltaSnapshot(
        updated_at=_dt.fromisoformat(payload["updated_at"].replace("Z", "+00:00")),
        sources_status=payload["sources_status"],
        data=payload["data"],
    )


def _build_bankerread_prompt(snapshot: EconDeltaSnapshot, today_iso: str) -> tuple[str, set[str]]:
    """Build the bankerread.txt prompt exactly as run_pipeline() does.

    Returns (prompt_str, fresh_ids).  Uses the fixture snapshot so the
    prompt is deterministic across debug runs.
    """
    from datetime import date as _date

    cfg = PipelineConfig(
        today=_date.fromisoformat(today_iso),
        enable_history=False,
        enable_headlines=False,
    )
    sections = gather(cfg, snapshot_override=snapshot)
    fresh_ids = {s.id for s in sections if s.freshness in ("fresh", "warning")}

    if not fresh_ids:
        raise RuntimeError(
            "No fresh/warning sections in fixture snapshot — "
            "cannot build bankerread_full prompt without section data."
        )

    fresh_payload = [s.model_dump(mode="json") for s in sections if s.id in fresh_ids]
    prompt = _fill(
        _load_prompt("bankerread.txt"),
        {
            "TODAY_ISO": today_iso,
            "SECTIONS_JSON": json.dumps(fresh_payload, default=str),
            "EXEC_SIGNALS_JSON": json.dumps({}, default=str),
        },
    )
    return prompt, fresh_ids


def _build_risk_map_prompt(snapshot: EconDeltaSnapshot, today_iso: str) -> str:
    """Build the risk_map_layout.txt prompt exactly as call_risk_map_layout() does.

    Uses the fixture snapshot and empty claude_outputs (no bankerread or exec_signals),
    which mirrors the minimal prod path that triggers the 14-vs-12 bug.
    """
    from datetime import date as _date

    cfg = PipelineConfig(
        today=_date.fromisoformat(today_iso),
        enable_history=False,
        enable_headlines=False,
    )
    sections = gather(cfg, snapshot_override=snapshot)
    bankerread_insights = {s.id: s.bankerread for s in sections if s.bankerread is not None}
    exec_signals: dict = {}

    payload = _build_risk_map_input(sections, exec_signals, bankerread_insights, today_iso)
    prompt = _fill(
        _load_prompt("risk_map_layout.txt"),
        {"INPUT_JSON": json.dumps(payload, default=str)},
    )
    return prompt


# ---------------------------------------------------------------------------
# Per-call dispatch
# ---------------------------------------------------------------------------

_CALL_TIMEOUT: dict[str, int] = {
    "bankerread_full": 1800,
    "risk_map_layout": 45,
}


def run_debug(call_name: str) -> Path:
    today_iso = now_bdt().date().isoformat()
    print(f"[debug_call] call={call_name!r}  today={today_iso}")

    try:
        snapshot = load_snapshot(
            str(_FIXTURE_SNAPSHOT)
        )
    except (EconDeltaUnavailable, Exception):
        snapshot = _load_fixture_snapshot()

    print("[debug_call] building prompt …", flush=True)
    if call_name == "bankerread_full":
        prompt, fresh_ids = _build_bankerread_prompt(snapshot, today_iso)
        print(f"[debug_call] fresh_ids = {sorted(fresh_ids)}")
    elif call_name == "risk_map_layout":
        prompt = _build_risk_map_prompt(snapshot, today_iso)
    else:
        raise ValueError(f"Unknown call: {call_name!r}. Choose: bankerread_full | risk_map_layout")

    timeout_s = _CALL_TIMEOUT[call_name]
    print(f"[debug_call] invoking run_max (timeout={timeout_s}s) …", flush=True)

    result = run_max(prompt=prompt, timeout_s=timeout_s)

    # Serialise MaxCallResult to a plain dict
    out: dict = {
        "call_name": call_name,
        "today_iso": today_iso,
        "raw_text": result.raw_text,
        "parsed": result.parsed,
        "usage": result.usage,
        "total_cost_usd": result.total_cost_usd,
        "duration_s": result.duration_s,
        "tokens": result.tokens,
        "prompt_length_chars": len(prompt),
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(f"/tmp/brief-debug-{call_name}-{ts}.json")
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

    print(f"[debug_call] wrote {out_path}")
    print(f"[debug_call] raw_text type: {type(result.parsed).__name__}")
    print(f"[debug_call] parsed preview: {repr(str(result.raw_text)[:300])}")
    print(f"[debug_call] cost: ${result.total_cost_usd}  tokens: {result.tokens}")

    return out_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture raw Claude Max output for failing pipeline calls."
    )
    parser.add_argument(
        "--call",
        required=True,
        choices=["bankerread_full", "risk_map_layout"],
        help="Which pipeline call to debug.",
    )
    args = parser.parse_args()

    out_path = run_debug(args.call)
    print(f"\nDone. Inspect with:\n  jq . {out_path}")


if __name__ == "__main__":
    main()
