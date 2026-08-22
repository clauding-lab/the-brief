"""Golden corpus tests — round-2 review item 5.

Fixtures under `tests/fixtures/real_issues/` are the REAL published rows for
issues #199-#204 (anon-fetched during the round-1 review), not synthetic
data. Two things follow from that:

1. Real published rows carry Supabase columns (`id`, `created_at`,
   `published_at`, `brief_id`) that `BriefPayloadV6`'s strict schema
   rejects — `_strip_db_extras` removes exactly those four keys, nothing
   else, so the fixture is otherwise byte-for-byte what was published.
2. There is no raw builder metadata (`unit`/`cadence`/`as_of`) attached to a
   published row — it was never stored past the point the editor consumed
   it. `_UNITS` below is sourced directly from the real builder specs
   (`bb.py`, `fx.py`, `dse.py`, `tbond.py`, `fiscal.py`, `macro.py`,
   `remit.py`, `banking.py`) rather than invented, and `as_of` per metric
   uses the published row's OWN `held_from` when stamped (a real vintage
   date) or the issue's `brief_date` otherwise — this is a best-effort
   reconstruction, not ground truth from a live Supabase read, so WARN
   counts here are an UPPER BOUND on real pipeline noise, not a precise
   measurement (see the bound's own comment below).

These tests exist to prove the SEVERITY SPLIT (round-2 review): the
count-claim check blocks ONLY the fiscal "fourteen reads/prints" phrasing
that is genuinely present in this corpus, nothing else ever blocks, and the
WARN volume stays within a sane order of magnitude (catching a future
regression that makes every figure warn, not asserting a precision level
this reconstruction can't actually measure).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from brief.v6_schema import BriefPayloadV6
from brief.validators.prose_numbers import (
    ProseNumberViolationError,
    check_count_claims,
    check_lede_numbers_against_builder_values,
    check_metric_sub_numbers,
    check_metric_sub_periods,
    check_metric_value_vs_raw,
    run_prose_number_gate,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "real_issues"
ISSUE_NUMBERS = (199, 200, 201, 202, 203, 204)

# (section slug, label) -> (unit, cadence) — copied from the real builder
# specs, not invented. Cross-referenced against bb.py, fx.py, dse.py,
# tbond.py, fiscal.py, macro.py, remit.py, banking.py at the time of this PR.
_UNITS: dict[tuple[str, str], tuple[str, str]] = {
    ("bb", "Overnight Call Money"): ("%", "event"),
    ("bb", "Call Money · 7-day"): ("%", "event"),
    ("bb", "Policy Rate"): ("%", "event"),
    ("bb", "SLF"): ("%", "event"),
    ("bb", "SDF"): ("%", "event"),
    ("bb", "Gross Reserves"): ("bn USD", "weekly"),
    ("banking", "NPL Ratio"): ("%", "quarterly"),
    ("banking", "CAR"): ("%", "quarterly"),
    ("fx", "USD/BDT mid"): ("BDT", "daily"),
    ("fx", "Gold"): ("USD/oz", "daily"),
    ("fx", "Gross Reserves"): ("bn USD", "weekly"),
    ("fx", "Monthly Exports"): ("bn USD", "monthly"),
    ("fx", "Trade Gap"): ("bn USD", "monthly"),
    ("dse", "DSEX close"): ("index", "daily"),
    ("dse", "DSEX %Δ"): ("%", "daily"),
    ("dse", "DS30"): ("index", "daily"),
    ("dse", "DSES"): ("index", "daily"),
    ("dse", "Turnover"): ("crore BDT", "daily"),
    ("dse", "Advancing"): ("stocks", "daily"),
    ("dse", "Declining"): ("stocks", "daily"),
    ("tbond", "91d T-Bill cut-off"): ("%", "event"),
    ("tbond", "182d T-Bill cut-off"): ("%", "event"),
    ("tbond", "364d T-Bill cut-off"): ("%", "event"),
    ("tbond", "5y Govt Bond"): ("%", "weekly"),
    ("tbond", "10y Govt Bond"): ("%", "weekly"),
    ("fiscal", "NBR collected YTD"): ("BDT trn", "monthly"),
    ("fiscal", "Govt bank borrow YTD"): ("BDT trn", "monthly"),
    ("macro", "CPI 12m Avg"): ("%", "monthly"),
    ("macro", "CPI Food (P-to-P)"): ("%", "monthly"),
    ("macro", "CPI Non-Food (P-to-P)"): ("%", "monthly"),
    ("macro", "Real Policy Rate"): ("%", "monthly"),
    ("macro", "REER"): ("index", "monthly"),
    ("macro", "Private Credit YoY"): ("%", "monthly"),
    ("macro", "M2 YoY"): ("%", "monthly"),
    ("macro", "Import Cover"): ("months", "monthly"),
    ("iran", "Brent spot"): ("USD/bbl", "daily"),
    ("iran", "WTI spot"): ("USD/bbl", "daily"),
    ("remit", "Monthly Remittance"): ("mn USD", "monthly"),
    ("headlines", "Headlines count"): ("items", "daily"),
}
# Remittance is the one label whose PUBLISHED value is known (from PR #165's
# own audit findings + AGENT_LEARNINGS.md) to sometimes diverge from the
# real builder value — reconstructing "raw" by re-parsing the published
# string would hide exactly the class of bug this module exists to catch.
_RAW_OVERRIDE: dict[tuple[str, str], float] = {("remit", "Monthly Remittance"): 2858.68}

_NUM_RE = re.compile(r"[\d,]+(?:\.\d+)?")


def _parse_published_value(printed: Any) -> float | None:
    if printed is None:
        return None
    s = str(printed)
    negative = s.strip().startswith(("−", "-"))
    m = _NUM_RE.search(s)
    if not m:
        return None
    v = float(m.group(0).replace(",", ""))
    return -v if negative else v


def _strip_db_extras(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    brief = dict(payload["brief"])
    for k in ("id", "created_at", "published_at"):
        brief.pop(k, None)
    payload["brief"] = brief
    payload["sections"] = [
        {k: v for k, v in s.items() if k not in ("id", "brief_id")}
        for s in payload["sections"]
    ]
    return payload


def _build_raw_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Best-effort raw-metadata reconstruction — see module docstring. Uses
    the metric's OWN `held_from` (a real stamped vintage date) when present,
    else the issue's `brief_date`, rather than one static date reused across
    every issue regardless of when it actually published."""
    brief_date = payload["brief"].get("brief_date", "2026-08-01")
    raw: list[dict[str, Any]] = []
    for s in payload["sections"]:
        metrics: list[dict[str, Any]] = []
        for m in s.get("metrics") or []:
            key = (s["slug"], m["label"])
            unit, cadence = _UNITS.get(key, ("", "daily"))
            value = _RAW_OVERRIDE.get(key, _parse_published_value(m.get("value")))
            metrics.append({
                "label": m["label"],
                "value": value,
                "unit": unit,
                "cadence": cadence,
                "as_of": m.get("held_from") or brief_date,
            })
        raw.append({"slug": s["slug"], "metrics": metrics})
    return raw


def _load_real_issue(issue_no: int) -> tuple[BriefPayloadV6, list[dict[str, Any]]]:
    path = FIXTURES_DIR / f"issue_{issue_no}.json"
    data = json.load(path.open())
    if isinstance(data, list):
        # A sections-only fetch (issues #199-#203) — synthesize the minimal
        # valid brief wrapper; issue_no/brief_date are load-bearing for
        # schema validity only, not for any check's logic.
        data = {
            "brief": {"issue_no": issue_no, "volume": 1, "brief_date": "2026-08-01"},
            "sections": data,
        }
    payload = _strip_db_extras(data)
    brief = BriefPayloadV6.model_validate(payload)
    raw = _build_raw_sections(payload)
    return brief, raw


# A future regression that makes every currency/percent figure warn would
# roughly double or triple this — not a precision claim on today's rate,
# since the reconstruction above is a best-effort stand-in for a live
# Supabase read (see module docstring). 150 comfortably clears the observed
# 79-112 range across this corpus while still catching that class of bug.
_SANE_WARN_BOUND = 150


@pytest.mark.parametrize("issue_no", ISSUE_NUMBERS)
def test_count_gate_blocks_only_the_fiscal_fourteen_reads_instance(issue_no: int) -> None:
    """Every one of #199-#204 genuinely contains fiscal's "fourteen
    reads/prints" phrasing (confirmed by a full-corpus scan during the
    round-2 review) — `check_count_claims` must block ALL SIX, and every
    block must be that SAME genuine phrase, in the fiscal section, never
    anything else."""
    brief, _raw = _load_real_issue(issue_no)
    with pytest.raises(ProseNumberViolationError) as exc_info:
        check_count_claims(brief)
    message = str(exc_info.value)
    assert "fiscal." in message
    assert "fourteen" in message
    assert "reads" in message or "prints" in message


@pytest.mark.parametrize("issue_no", ISSUE_NUMBERS)
def test_orchestrator_blocks_via_count_claim_not_some_other_path(issue_no: int) -> None:
    """The gate must fail CLOSED for the right reason — confirms
    `run_prose_number_gate` (the actual pipeline wiring's entry point) blocks
    each of these issues specifically on the count-claim, not on some
    incidental sub-number/period mismatch elsewhere firing first."""
    brief, raw = _load_real_issue(issue_no)
    with pytest.raises(ProseNumberViolationError) as exc_info:
        run_prose_number_gate(brief, raw, strict=False)
    assert "count-claim" in str(exc_info.value)


@pytest.mark.parametrize("issue_no", ISSUE_NUMBERS)
def test_warn_totals_per_issue_stay_within_a_sane_bound(issue_no: int) -> None:
    """WARN-mode volume across all four non-blocking checks, summed. See
    `_SANE_WARN_BOUND`'s comment — this catches a gross regression, it does
    not certify a specific false-positive rate."""
    brief, raw = _load_real_issue(issue_no)
    raw_by_slug = {r["slug"]: r for r in raw}
    total = (
        len(check_metric_sub_numbers(brief, raw_by_slug))
        + len(check_metric_sub_periods(brief, raw_by_slug))
        + len(check_metric_value_vs_raw(brief, raw_by_slug))
        + len(check_lede_numbers_against_builder_values(brief, raw))
    )
    assert total <= _SANE_WARN_BOUND, (
        f"issue {issue_no}: {total} WARN-mode findings exceeds the sane bound "
        f"of {_SANE_WARN_BOUND} — investigate before assuming this is more noise"
    )


def test_issues_without_the_fiscal_phrase_would_not_block() -> None:
    """Negative control: strip the count-claim phrase out of one real
    issue's fiscal section and confirm the gate no longer blocks it on
    count-claims — proves the check is discriminating on the phrase, not
    firing unconditionally on every fiscal section."""
    brief, _raw = _load_real_issue(204)
    fiscal = next(s for s in brief.sections if s.slug == "fiscal")
    if fiscal.tldr and "fourteen" in fiscal.tldr:
        fiscal.tldr = "NBR collections remain flat this month."
    if fiscal.banker_read is not None:
        fiscal.banker_read.verdict = re.sub(
            r"across fourteen (reads|prints)", "with no fresh print",
            fiscal.banker_read.verdict,
        )
        fiscal.banker_read.watch = [
            re.sub(r"in fourteen (reads|prints)", "soon", w)
            for w in fiscal.banker_read.watch
        ]
    for m in fiscal.metrics:
        if m.sub and "fourteen" in m.sub:
            m.sub = re.sub(r"(across|for|in) fourteen (reads|prints)", "unchanged", m.sub)
    check_count_claims(brief)  # must not raise once the phrase is gone
