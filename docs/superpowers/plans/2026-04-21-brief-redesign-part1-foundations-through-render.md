# The Brief Redesign — Part 1 (Foundations → Render) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `the-brief` as a data-driven pipeline — Python owns gathering, contracts, and rendering; Claude Max owns three small JSON narrative calls — producing a byte-comparable `index.html` to the current GHA output.

**Architecture:** A new `brief/` package runs `gather → assemble SectionData → 3 Claude calls → render → persist`. Each of 14 builders produces a typed `SectionData` from EconDelta's `latest.json`, Supabase `metric_history`, and a headline scraper. Three Claude calls (`headlines_curation`, `exec_signals`, `bankerread_insights`) emit small validated JSON blobs that Python splices into per-section JSX fragments, which `render/assemble.py` threads into the existing `the-brief.html` shell.

**Tech Stack:** Python 3.11, Pydantic v2, pytest + pytest-cov, `subprocess` for `claude -p`, `urllib` for Supabase PostgREST, existing `build.sh` / `the-brief.html` unchanged. No new Python dependencies beyond `pydantic`.

---

## File Structure

### New files (all under `~/Projects/clauding-lab/the-brief/`)

```
brief/
  __init__.py
  schema.py              # Pydantic models: Metric, Delta, NewsItem, BankerReadInsight, ExecSignal, SectionData
  cadence.py             # CadenceKind/FreshnessKind, metric_freshness, section_freshness, trading-day logic
  econdelta.py           # Read EconDelta latest.json (file-path driven; test-injectable)
  history.py             # Supabase metric_history read/write + delta computation
  headlines.py           # Port _scrape_headlines from update.py
  pipeline.py            # gather() orchestrator: calls every builder, runs Claude, renders, writes
  report.py              # run_report.json writer + Discord notify
  builders/
    __init__.py          # SPINE_BUILDERS / KEEP_BUILDERS registries
    bb.py                # Spine
    macro.py             # Spine
    fx.py                # Spine
    remittance.py        # Spine
    dse.py               # Spine
    tbond.py             # Spine
    iranwar.py           # Spine
    headlines.py         # Spine (consumes Call 1 output)
    exec.py              # Spine (consumes other sections + Call 2 output)
    comm.py              # Keep
    banking.py           # Keep
    dam.py               # Keep
    fiscal.py            # Keep
    nbr.py               # Keep
  claude/
    __init__.py
    max_client.py        # subprocess wrapper around `claude -p`, timeout/retry
    validators.py        # 3 validators: curation, signals, insights (+ stale variant)
    prompts/
      headlines_curation.txt
      exec_signals.txt
      bankerread.txt
      bankerread_stale.txt
  render/
    __init__.py
    assemble.py          # Splice per-section JSX into the-brief.html shell; drop cut sections
    templates/
      __init__.py
      section_bb.py      # render_section_bb(SectionData) -> str
      section_macro.py
      section_fx.py
      section_remittance.py
      section_dse.py
      section_tbond.py
      section_iranwar.py
      section_headlines.py
      section_exec.py
      section_comm.py
      section_banking.py
      section_dam.py
      section_fiscal.py
      section_nbr.py
      _jsx.py            # JSX escaping + BankerRead fragment helpers (shared)
tests/
  __init__.py
  conftest.py            # shared fixtures (fake EconDelta JSON, fake Supabase, sample HTML shell)
  test_schema.py
  test_cadence.py
  test_econdelta.py
  test_history.py
  test_headlines.py
  builders/
    __init__.py
    test_bb.py
    test_fx.py
    test_dse.py
    test_builders_smoke.py   # shape-level coverage for the remaining 11 builders
  claude/
    test_max_client.py
    test_validators.py
  render/
    test_assemble.py
    test_templates_smoke.py  # shape-level coverage for all section templates
  test_pipeline_integration.py
fixtures/
  econdelta_latest.json
  metric_history_seed.json
  sample_the_brief.html    # small-scale copy of the shell, ~200 lines, for fast render tests
pytest.ini
requirements-dev.txt       # pytest + pytest-cov (dev only; stays out of the production image)
```

### Modified files

- `requirements.txt` — add `pydantic>=2`.
- `update.py` — at the bottom of the plan's Part 1 this remains untouched; Part 2 ops plan swaps the entrypoint. Keep side-by-side.

### Responsibility boundaries

- **`brief/schema.py`**: data contracts only. No IO, no cadence maths.
- **`brief/cadence.py`**: pure functions over `Metric` / `SectionData`. No clock calls except through a passed-in `now` arg.
- **`brief/econdelta.py`**: reads `/home/adnan/econdelta/data/latest.json` (path overridable via env/arg). Never calls Claude or Supabase.
- **`brief/history.py`**: Supabase `metric_history` upserts + last-known reads. No builder logic.
- **`brief/builders/*.py`**: each exposes `build(ctx: BuilderContext) -> SectionData`. `BuilderContext` wraps the EconDelta snapshot, history client, `now`, and (for late-phase builders) the Claude outputs. No builder talks to Claude directly.
- **`brief/claude/max_client.py`**: one function `run_max(prompt: str, *, timeout_s: int) -> dict`. Subprocess only, no business logic.
- **`brief/render/assemble.py`**: shell parsing + brace-balanced function-body substitution. No data knowledge.
- **`brief/render/templates/*.py`**: one `render(section: SectionData) -> str` per section. Pure functions.

---

## Conventions

- **Timestamps**: all `as_of`-like timestamps are UTC unless explicitly `_bdt`. `now_bdt()` in `brief/cadence.py` returns `datetime.now(timezone(timedelta(hours=6)))`.
- **IDs**: section IDs are short, lowercase, no underscore: `bb`, `macro`, `fx`, `remit`, `dse`, `tbond`, `iranwar`, `headlines`, `exec`, `comm`, `banking`, `dam`, `fiscal`, `nbr`.
- **Metric IDs**: `snake_case`, globally unique, e.g. `bb_policy_rate`, `dse_dsex_close`, `fx_usd_bdt_mid`.
- **Commit style**: `feat(brief): …`, `test(brief): …`, `refactor(brief): …`. One logical change per commit.
- **Branch**: `feat/redesign-data-driven` (already pushed; this plan lands additional commits).
- **Python version**: 3.11 (system default on macOS Sonoma + Debian 12 VPS).

---

## Phase 1 — Scaffolding (~3h)

Establish the `brief/` package skeleton, schema, cadence, and a green test suite. No EconDelta or Supabase reads yet; all data passed in as dicts.

### Task 1.1 — Initialize package + test harness

**Files:**
- Create: `brief/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/builders/__init__.py`
- Create: `tests/claude/__init__.py`
- Create: `tests/render/__init__.py`
- Create: `pytest.ini`
- Create: `requirements-dev.txt`
- Modify: `requirements.txt`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p brief/builders brief/claude/prompts brief/render/templates
mkdir -p tests/builders tests/claude tests/render fixtures
touch brief/__init__.py brief/builders/__init__.py brief/claude/__init__.py brief/render/__init__.py brief/render/templates/__init__.py
touch tests/__init__.py tests/builders/__init__.py tests/claude/__init__.py tests/render/__init__.py
```

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
addopts = -q --cov=brief --cov-report=term-missing --cov-fail-under=80
markers =
    integration: end-to-end tests that shell out or hit Supabase
```

- [ ] **Step 3: Write `requirements-dev.txt`**

```
pytest>=8
pytest-cov>=5
```

- [ ] **Step 4: Append `pydantic>=2` to `requirements.txt`**

Final contents:

```
anthropic>=0.84
pydantic>=2
```

- [ ] **Step 5: Create venv + install**

Run:

```bash
cd ~/Projects/clauding-lab/the-brief
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

Expected: `pydantic` and `pytest` installed; no errors.

- [ ] **Step 6: Sanity-check pytest sees the empty suite**

Run: `pytest`
Expected: `0 tests collected` or similar; exit code 5 (no tests) is acceptable at this stage.

- [ ] **Step 7: Commit**

```bash
git add brief/ tests/ fixtures/ pytest.ini requirements.txt requirements-dev.txt
git commit -m "feat(brief): scaffold brief/ package + pytest harness"
```

### Task 1.2 — Schema: core types + `Metric`

**Files:**
- Create: `brief/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_schema.py`:

```python
from datetime import date
import pytest
from pydantic import ValidationError

from brief.schema import Delta, Metric


def test_metric_minimal_valid():
    m = Metric(
        id="bb_policy_rate",
        label="Policy Rate",
        value=10.0,
        unit="%",
        as_of=date(2026, 4, 18),
        source="BB",
        cadence="event",
    )
    assert m.id == "bb_policy_rate"
    assert m.delta is None
    assert m.source_url is None


def test_metric_accepts_str_value():
    m = Metric(
        id="fx_usd_bdt_mid",
        label="USD/BDT mid",
        value="122.70",
        unit="BDT",
        as_of=date(2026, 4, 20),
        source="BB",
        cadence="daily",
    )
    assert m.value == "122.70"


def test_metric_rejects_unknown_cadence():
    with pytest.raises(ValidationError):
        Metric(
            id="x",
            label="x",
            value=1,
            unit="%",
            as_of=date(2026, 1, 1),
            source="x",
            cadence="yearly",  # not in CadenceKind
        )


def test_delta_requires_direction_literal():
    d = Delta(value=0.3, direction="up", window="wow")
    assert d.direction == "up"
    with pytest.raises(ValidationError):
        Delta(value=0.3, direction="north", window="wow")
```

- [ ] **Step 2: Run test — verify it fails**

Run: `pytest tests/test_schema.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'brief.schema'`).

- [ ] **Step 3: Implement `brief/schema.py`**

```python
"""Pydantic data contracts for The Brief."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

CadenceKind = Literal["daily", "weekly", "monthly", "quarterly", "event"]
FreshnessKind = Literal["fresh", "warning", "stale", "pending", "unavailable"]
DirectionKind = Literal["up", "down", "flat"]
SignalKind = Literal["bull", "bear", "warn", "watch"]
DeltaWindow = Literal["dod", "wow", "mom", "yoy"]


class Delta(BaseModel):
    value: float
    direction: DirectionKind
    window: DeltaWindow


class Metric(BaseModel):
    id: str
    label: str
    value: float | int | str | None
    unit: str
    as_of: date
    source: str
    source_url: Optional[str] = None
    cadence: CadenceKind
    delta: Optional[Delta] = None


class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published: datetime


class BankerReadInsight(BaseModel):
    sentences: list[str]
    generated_at: datetime
    variant: Literal["full", "stale_micro"] = "full"


class ExecSignal(BaseModel):
    direction: SignalKind
    text: str = Field(..., max_length=200)
    section_anchor: str


class SectionData(BaseModel):
    id: str
    title: str
    metrics: list[Metric] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    freshness: FreshnessKind
    freshness_reason: Optional[str] = None
    bankerread: Optional[BankerReadInsight] = None
    exec_signals: Optional[list[ExecSignal]] = None
```

- [ ] **Step 4: Run test — verify it passes**

Run: `pytest tests/test_schema.py -v`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add brief/schema.py tests/test_schema.py
git commit -m "feat(brief): add schema.py with Pydantic data contracts"
```

### Task 1.3 — Schema: `SectionData`, `BankerReadInsight`, `ExecSignal` tests

**Files:**
- Test: `tests/test_schema.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_schema.py`:

```python
from datetime import datetime, timezone

from brief.schema import (
    BankerReadInsight,
    ExecSignal,
    NewsItem,
    SectionData,
)


def test_section_data_defaults():
    s = SectionData(id="bb", title="Policy & Rates", freshness="fresh")
    assert s.metrics == []
    assert s.news == []
    assert s.bankerread is None
    assert s.exec_signals is None


def test_bankerread_full_variant():
    br = BankerReadInsight(
        sentences=["a", "b", "c", "d"],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    assert br.variant == "full"


def test_bankerread_stale_variant():
    br = BankerReadInsight(
        sentences=["no fresh data; headlines suggest x"],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        variant="stale_micro",
    )
    assert br.variant == "stale_micro"
    assert len(br.sentences) == 1


def test_exec_signal_shape():
    e = ExecSignal(direction="bull", text="Reserves up 0.3 bn WoW", section_anchor="bb")
    assert e.direction == "bull"
    assert e.section_anchor == "bb"


def test_news_item_parses_isoformat():
    n = NewsItem(
        title="x",
        url="https://example.com/x",
        source="DS",
        published=datetime(2026, 4, 21, 6, 0, tzinfo=timezone.utc),
    )
    assert n.source == "DS"
```

- [ ] **Step 2: Run — expect PASS (schema already supports these)**

Run: `pytest tests/test_schema.py -v`
Expected: PASS (all 9).

- [ ] **Step 3: Commit**

```bash
git add tests/test_schema.py
git commit -m "test(brief): cover SectionData + BankerRead + ExecSignal shapes"
```

### Task 1.4 — Cadence: trading-day helpers

**Files:**
- Create: `brief/cadence.py`
- Test: `tests/test_cadence.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cadence.py`:

```python
from datetime import date, datetime, timezone, timedelta

from brief.cadence import is_bd_trading_day, trading_days_between


def test_is_bd_trading_day_sunday_true():
    # 2026-04-19 is Sunday (BD trading day)
    assert is_bd_trading_day(date(2026, 4, 19)) is True


def test_is_bd_trading_day_friday_false():
    # 2026-04-17 is Friday (weekend in BD)
    assert is_bd_trading_day(date(2026, 4, 17)) is False


def test_is_bd_trading_day_saturday_false():
    assert is_bd_trading_day(date(2026, 4, 18)) is False


def test_trading_days_between_skips_weekend():
    # Thu 2026-04-16 to Sun 2026-04-19: Thu, Sun = 1 trading day gap
    assert trading_days_between(date(2026, 4, 16), date(2026, 4, 19)) == 1


def test_trading_days_between_same_day_zero():
    assert trading_days_between(date(2026, 4, 20), date(2026, 4, 20)) == 0


def test_trading_days_between_across_week():
    # Sun 2026-04-12 → Sun 2026-04-19 = 5 trading days gap (Mon,Tue,Wed,Thu,Sun)
    assert trading_days_between(date(2026, 4, 12), date(2026, 4, 19)) == 5
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/test_cadence.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `brief/cadence.py` (partial)**

```python
"""Cadence + freshness computation for The Brief.

BD trading week is Sun–Thu. `fresh` thresholds are cadence-specific;
trading-day awareness applies only to `daily`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from brief.schema import CadenceKind, FreshnessKind, Metric

_BDT = timezone(timedelta(hours=6))

# Sun=6, Mon=0, Tue=1, Wed=2, Thu=3 → BD trading days
_BD_TRADING_WEEKDAYS = {6, 0, 1, 2, 3}


def now_bdt() -> datetime:
    """Clock seam for tests — replace via monkeypatch."""
    return datetime.now(_BDT)


def is_bd_trading_day(d: date) -> bool:
    return d.weekday() in _BD_TRADING_WEEKDAYS


def trading_days_between(start: date, end: date) -> int:
    """Count BD trading days strictly between start and end (inclusive of end, excluding start)."""
    if end <= start:
        return 0
    count = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if is_bd_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count
```

- [ ] **Step 4: Run — verify it passes**

Run: `pytest tests/test_cadence.py -v`
Expected: PASS (6/6).

- [ ] **Step 5: Commit**

```bash
git add brief/cadence.py tests/test_cadence.py
git commit -m "feat(brief): add cadence trading-day helpers"
```

### Task 1.5 — Cadence: `metric_freshness`

**Files:**
- Modify: `brief/cadence.py`
- Test: `tests/test_cadence.py` (append)

- [ ] **Step 1: Append the failing tests**

```python
from brief.cadence import metric_freshness
from brief.schema import Metric


def _m(mid: str, as_of: date, cadence: CadenceKind = "daily", value=1.0) -> Metric:
    return Metric(id=mid, label=mid, value=value, unit="x", as_of=as_of,
                  source="t", cadence=cadence)


def test_daily_fresh_within_one_trading_day():
    today = date(2026, 4, 21)  # Tuesday
    m = _m("x", date(2026, 4, 20), "daily")  # Monday
    assert metric_freshness(m, today=today) == "fresh"


def test_daily_warning_at_two_trading_days():
    today = date(2026, 4, 22)  # Wednesday
    m = _m("x", date(2026, 4, 19), "daily")  # Sunday
    # Trading days between Sun 04-19 and Wed 04-22 = Mon,Tue,Wed = 3 → stale? spec says >2 trading days
    assert metric_freshness(m, today=today) == "stale"


def test_daily_thursday_close_still_fresh_on_saturday():
    # DSE closes Thu; Sat run should see Thursday's value as fresh (0 trading days passed)
    today = date(2026, 4, 18)  # Saturday
    m = _m("dse", date(2026, 4, 16), "daily")  # Thursday
    assert metric_freshness(m, today=today) == "fresh"


def test_weekly_fresh_under_7_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 17), "weekly")
    assert metric_freshness(m, today=today) == "fresh"


def test_weekly_stale_over_10_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 10), "weekly")
    assert metric_freshness(m, today=today) == "stale"


def test_monthly_fresh_under_35_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 3, 20), "monthly")
    assert metric_freshness(m, today=today) == "fresh"


def test_monthly_stale_over_45_days():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 2, 20), "monthly")
    assert metric_freshness(m, today=today) == "stale"


def test_event_always_fresh():
    today = date(2026, 4, 21)
    m = _m("x", date(2025, 1, 1), "event")
    assert metric_freshness(m, today=today) == "fresh"


def test_metric_with_none_value_is_unavailable():
    today = date(2026, 4, 21)
    m = _m("x", date(2026, 4, 20), "daily", value=None)
    assert metric_freshness(m, today=today) == "unavailable"
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/test_cadence.py -v`
Expected: FAIL (metric_freshness missing).

- [ ] **Step 3: Append to `brief/cadence.py`**

```python
# ── cadence thresholds (spec §6) ──────────────────────────────────────────────
_THRESHOLDS = {
    # cadence: (fresh_max, warning_max)   # stale if > warning_max
    "weekly":    (7, 10),
    "monthly":   (35, 45),
    "quarterly": (95, 120),
}


def metric_freshness(metric: Metric, *, today: date | None = None) -> FreshnessKind:
    """Freshness per spec §6. Trading-day-aware for daily cadence only."""
    if today is None:
        today = now_bdt().date()

    if metric.value is None:
        return "unavailable"

    if metric.cadence == "event":
        return "fresh"

    if metric.cadence == "daily":
        gap = trading_days_between(metric.as_of, today)
        if gap <= 1:
            return "fresh"
        if gap <= 2:
            return "warning"
        return "stale"

    if metric.cadence in _THRESHOLDS:
        days = (today - metric.as_of).days
        fresh_max, warn_max = _THRESHOLDS[metric.cadence]
        if days <= fresh_max:
            return "fresh"
        if days <= warn_max:
            return "warning"
        return "stale"

    # Unknown cadence — conservative
    return "unavailable"
```

- [ ] **Step 4: Run — verify it passes**

Run: `pytest tests/test_cadence.py -v`
Expected: PASS (all 15).

- [ ] **Step 5: Commit**

```bash
git add brief/cadence.py tests/test_cadence.py
git commit -m "feat(brief): add metric_freshness with trading-day daily logic"
```

### Task 1.6 — Cadence: `section_freshness`

**Files:**
- Modify: `brief/cadence.py`
- Test: `tests/test_cadence.py` (append)

- [ ] **Step 1: Append failing tests**

```python
from brief.cadence import section_freshness


def test_section_freshness_empty_is_fresh():
    assert section_freshness([]) == "fresh"


def test_section_freshness_worst_unavailable_wins():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 4, 20), "daily"),                      # fresh
        _m("b", date(2026, 4, 20), "daily", value=None),          # unavailable
        _m("c", date(2026, 3, 1), "monthly"),                     # warning/stale
    ]
    assert section_freshness(metrics, today=today) == "unavailable"


def test_section_freshness_stale_beats_warning():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 2, 20), "monthly"),  # stale
        _m("b", date(2026, 3, 20), "monthly"),  # fresh
    ]
    assert section_freshness(metrics, today=today) == "stale"


def test_section_freshness_all_fresh():
    today = date(2026, 4, 21)
    metrics = [
        _m("a", date(2026, 4, 20), "daily"),
        _m("b", date(2026, 4, 15), "weekly"),
    ]
    assert section_freshness(metrics, today=today) == "fresh"
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/test_cadence.py -v -k section_freshness`
Expected: FAIL.

- [ ] **Step 3: Append to `brief/cadence.py`**

```python
def section_freshness(
    metrics: Iterable[Metric], *, today: date | None = None
) -> FreshnessKind:
    """Section freshness = worst metric freshness (spec §4)."""
    states = [metric_freshness(m, today=today) for m in metrics]
    for worst in ("unavailable", "stale", "pending", "warning"):
        if worst in states:
            return worst  # type: ignore[return-value]
    return "fresh"
```

- [ ] **Step 4: Run — verify all cadence tests pass**

Run: `pytest tests/test_cadence.py -v`
Expected: PASS (all tests, including the 4 new ones).

- [ ] **Step 5: Commit**

```bash
git add brief/cadence.py tests/test_cadence.py
git commit -m "feat(brief): add section_freshness = worst-metric-wins"
```

### Task 1.7 — Builder context stub + registry

**Files:**
- Create: `brief/builders/__init__.py` (overwrite)
- Test: `tests/builders/test_registry.py`

- [ ] **Step 1: Write failing test**

`tests/builders/test_registry.py`:

```python
from brief.builders import SPINE_BUILDER_IDS, KEEP_BUILDER_IDS, ALL_BUILDER_IDS


def test_spine_ids_are_9():
    assert SPINE_BUILDER_IDS == (
        "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
        "headlines", "exec",
    )


def test_keep_ids_are_5():
    assert KEEP_BUILDER_IDS == ("comm", "banking", "dam", "fiscal", "nbr")


def test_all_union_is_disjoint():
    assert set(SPINE_BUILDER_IDS).isdisjoint(KEEP_BUILDER_IDS)
    assert set(ALL_BUILDER_IDS) == set(SPINE_BUILDER_IDS) | set(KEEP_BUILDER_IDS)
```

- [ ] **Step 2: Run — verify it fails**

Run: `pytest tests/builders/test_registry.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `brief/builders/__init__.py`**

```python
"""Registry for section builders.

Spine = must ship daily; graceful-stale allowed but never dropped.
Keep  = useful context; may degrade silently to last-known or unavailable.
"""
from __future__ import annotations

SPINE_BUILDER_IDS: tuple[str, ...] = (
    "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
    "headlines", "exec",
)

KEEP_BUILDER_IDS: tuple[str, ...] = ("comm", "banking", "dam", "fiscal", "nbr")

ALL_BUILDER_IDS: tuple[str, ...] = SPINE_BUILDER_IDS + KEEP_BUILDER_IDS
```

- [ ] **Step 4: Run — verify it passes**

Run: `pytest tests/builders/test_registry.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add brief/builders/__init__.py tests/builders/test_registry.py
git commit -m "feat(brief): add builder registry (9 spine + 5 keep)"
```

### Task 1.8 — Phase 1 exit gate

- [ ] **Step 1: Full test run with coverage**

Run: `pytest`
Expected: all tests PASS, coverage ≥80% for `brief/schema.py` and `brief/cadence.py`.

- [ ] **Step 2: Import smoke test**

Run: `python -c "from brief.schema import SectionData; from brief.cadence import section_freshness; print(section_freshness([]))"`
Expected: `fresh`.

- [ ] **Step 3: Commit a Phase 1 marker (optional)**

```bash
git commit --allow-empty -m "chore(brief): Phase 1 scaffolding complete"
```

---

## Phase 2 — Builders (~4h)

Implement the data side of the pipeline: read EconDelta, read/write Supabase `metric_history`, scrape headlines, build all 14 `SectionData` objects, and wire `pipeline.gather()`.

### Task 2.1 — Fixture: canonical EconDelta JSON

**Files:**
- Create: `fixtures/econdelta_latest.json`

- [ ] **Step 1: Write the fixture (trimmed but valid)**

`fixtures/econdelta_latest.json`:

```json
{
  "schema_version": "1.0",
  "updated_at": "2026-04-21T00:20:19.710498Z",
  "sources_status": {
    "bb_forex":         {"status": "ok", "last_success": "2026-04-21T00:15:00Z", "age_hours": 0.08, "url": "https://www.bb.org.bd/en/index.php/econdata/exchangerate", "error": null},
    "dse_market":       {"status": "ok", "last_success": "2026-04-20T10:30:00Z", "age_hours": 6.94, "url": "https://www.dse.com.bd/market-statistics.php", "error": null},
    "commodity_prices": {"status": "ok", "last_success": "2026-04-21T00:08:40Z", "age_hours": 0.19, "url": null, "error": null}
  },
  "data": {
    "usd_bdt_mid": 122.70,
    "usd_bdt_buy": 122.60,
    "usd_bdt_sell": 122.80,
    "eur_bdt": 144.34,
    "gbp_bdt": 165.85,
    "gross_reserves_usd_bn": 34.1166,
    "import_cover_months": null,
    "reserves_date": "2026-03-01",
    "trading_day": true,
    "dsex": 5232.49,
    "dsex_change": -15.05,
    "dsex_change_pct": -0.29,
    "ds30": 1980.01,
    "dses": 1059.70,
    "turnover_crore": 824.76,
    "total_trades": 223903,
    "advancing": 120,
    "declining": 207,
    "unchanged": 62,
    "brent_crude_usd_barrel": 95.23,
    "wti_crude_usd_barrel": 87.05,
    "gold_usd_oz": 4820.90,
    "commodity_change_pct": {
      "brent_crude": 0.0537,
      "wti_crude": 0.0540,
      "gold": 0.0016
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add fixtures/econdelta_latest.json
git commit -m "test(brief): canonical EconDelta latest.json fixture"
```

### Task 2.2 — `brief/econdelta.py`: snapshot reader

**Files:**
- Create: `brief/econdelta.py`
- Test: `tests/test_econdelta.py`

- [ ] **Step 1: Write the failing test**

`tests/test_econdelta.py`:

```python
import json
from datetime import date
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot, load_snapshot, EconDeltaUnavailable

FIXTURE = Path(__file__).parent.parent / "fixtures" / "econdelta_latest.json"


def test_load_snapshot_from_fixture():
    snap = load_snapshot(FIXTURE)
    assert isinstance(snap, EconDeltaSnapshot)
    assert snap.data["usd_bdt_mid"] == 122.70
    assert snap.sources_status["bb_forex"]["status"] == "ok"
    assert snap.updated_at.year == 2026


def test_get_helper_returns_none_for_missing_key():
    snap = load_snapshot(FIXTURE)
    assert snap.get("nope_key") is None
    assert snap.get("usd_bdt_mid") == 122.70


def test_source_age_hours():
    snap = load_snapshot(FIXTURE)
    assert snap.source_age_hours("bb_forex") == 0.08
    assert snap.source_age_hours("does_not_exist") is None


def test_missing_file_raises_unavailable(tmp_path):
    with pytest.raises(EconDeltaUnavailable):
        load_snapshot(tmp_path / "missing.json")


def test_bad_json_raises_unavailable(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid")
    with pytest.raises(EconDeltaUnavailable):
        load_snapshot(bad)
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/test_econdelta.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement `brief/econdelta.py`**

```python
"""Read EconDelta's `latest.json` snapshot from a co-located file path.

The VPS Brief pipeline reads `/home/adnan/econdelta/data/latest.json` directly;
tests pass a path to a fixture. No HTTP.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(os.environ.get("ECONDELTA_DATA", "/home/adnan/econdelta/data/latest.json"))


class EconDeltaUnavailable(Exception):
    """Raised when the snapshot can't be read or parsed."""


@dataclass(frozen=True)
class EconDeltaSnapshot:
    updated_at: datetime
    sources_status: dict[str, dict[str, Any]]
    data: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def source_age_hours(self, source_id: str) -> float | None:
        s = self.sources_status.get(source_id)
        if not s:
            return None
        v = s.get("age_hours")
        return float(v) if v is not None else None

    def source_status(self, source_id: str) -> str | None:
        s = self.sources_status.get(source_id)
        return s.get("status") if s else None


def load_snapshot(path: Path | str = DEFAULT_PATH) -> EconDeltaSnapshot:
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot not found: {p}") from e
    except json.JSONDecodeError as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot unparseable: {p}: {e}") from e

    try:
        updated_at = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
        return EconDeltaSnapshot(
            updated_at=updated_at,
            sources_status=payload.get("sources_status", {}),
            data=payload.get("data", {}),
        )
    except (KeyError, ValueError) as e:
        raise EconDeltaUnavailable(f"EconDelta snapshot malformed: {e}") from e
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_econdelta.py -v`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add brief/econdelta.py tests/test_econdelta.py
git commit -m "feat(brief): EconDelta snapshot reader with file path seam"
```

### Task 2.3 — `brief/history.py`: Supabase `metric_history` client

**Files:**
- Create: `brief/history.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: Write the failing test**

`tests/test_history.py`:

```python
from datetime import date
from unittest.mock import MagicMock

from brief.history import MetricHistoryClient, HistoryRow


def _client(mock_http):
    return MetricHistoryClient(
        url="https://example.supabase.co",
        service_key="svc",
        http=mock_http,
    )


def test_get_latest_returns_row(monkeypatch):
    mock = MagicMock()
    mock.get.return_value = (200, [{"metric_id": "x", "as_of": "2026-04-20",
                                    "value": 10.0, "source": "BB",
                                    "ingested_at": "2026-04-20T00:00:00Z"}])
    c = _client(mock)
    row = c.get_latest("x")
    assert row == HistoryRow(
        metric_id="x", as_of=date(2026, 4, 20), value=10.0, source="BB"
    )
    mock.get.assert_called_once()


def test_get_latest_returns_none_when_empty():
    mock = MagicMock()
    mock.get.return_value = (200, [])
    c = _client(mock)
    assert c.get_latest("x") is None


def test_upsert_many_calls_post():
    mock = MagicMock()
    mock.post.return_value = (201, None)
    c = _client(mock)
    c.upsert_many([
        HistoryRow("a", date(2026, 4, 20), 1, "BB"),
        HistoryRow("b", date(2026, 4, 20), 2, "BB"),
    ])
    mock.post.assert_called_once()
    args, kwargs = mock.post.call_args
    body = kwargs["json"]
    assert len(body) == 2
    assert body[0]["metric_id"] == "a"


def test_upsert_many_noop_on_empty():
    mock = MagicMock()
    c = _client(mock)
    c.upsert_many([])
    mock.post.assert_not_called()
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/test_history.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/history.py`**

```python
"""Supabase `metric_history` client — HTTP seam, JSON body.

Abstracts PostgREST so tests inject a mock `http` object with `.get()`/`.post()`
returning `(status, json_body_or_none)`. Production passes a urllib wrapper.
"""
from __future__ import annotations

import json as _json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class HistoryRow:
    metric_id: str
    as_of: date
    value: Any
    source: str


@runtime_checkable
class HttpClient(Protocol):
    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]: ...
    def post(self, url: str, *, headers: dict[str, str], json: Any) -> tuple[int, Any]: ...


class UrllibHttp:
    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, _json.loads(resp.read() or b"null")

    def post(self, url: str, *, headers: dict[str, str], json: Any) -> tuple[int, Any]:
        req = urllib.request.Request(
            url,
            data=_json.dumps(json).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            return resp.status, (_json.loads(body) if body else None)


class MetricHistoryClient:
    def __init__(self, *, url: str, service_key: str, http: HttpClient | None = None):
        self.url = url.rstrip("/")
        self.key = service_key
        self.http = http or UrllibHttp()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def get_latest(self, metric_id: str) -> HistoryRow | None:
        q = urllib.parse.urlencode({
            "metric_id": f"eq.{metric_id}",
            "select":    "metric_id,as_of,value,source,ingested_at",
            "order":     "as_of.desc",
            "limit":     "1",
        })
        url = f"{self.url}/rest/v1/metric_history?{q}"
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return None
        row = body[0]
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=row["value"],
            source=row["source"],
        )

    def upsert_many(self, rows: list[HistoryRow]) -> bool:
        if not rows:
            return True
        url = f"{self.url}/rest/v1/metric_history?on_conflict=metric_id,as_of"
        payload = [
            {"metric_id": r.metric_id, "as_of": r.as_of.isoformat(),
             "value": r.value, "source": r.source}
            for r in rows
        ]
        status, _ = self.http.post(
            url,
            headers=self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=payload,
        )
        return status in (200, 201, 204)
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_history.py -v`
Expected: PASS (4/4).

- [ ] **Step 5: Commit**

```bash
git add brief/history.py tests/test_history.py
git commit -m "feat(brief): MetricHistoryClient with HTTP seam"
```

### Task 2.4 — Supabase migration: `metric_history` table

**Files:**
- Create: `migrations/0001_metric_history.sql`

- [ ] **Step 1: Write SQL**

```sql
-- migrations/0001_metric_history.sql
-- Last-known metric values + provenance.

create table if not exists public.metric_history (
  metric_id    text        not null,
  as_of        date        not null,
  value        jsonb       not null,
  source       text        not null,
  ingested_at  timestamptz not null default now(),
  primary key (metric_id, as_of)
);

create index if not exists metric_history_lookup
  on public.metric_history (metric_id, as_of desc);

-- RLS: service key only. No anon / authenticated access.
alter table public.metric_history enable row level security;
```

- [ ] **Step 2: Manually apply (one-shot; note this is ops, not test)**

Run in Supabase SQL editor (or via the Supabase MCP `apply_migration` with name `metric_history_init` and this body). The implementer documents execution in the commit message; do not check the SQL result into tests.

- [ ] **Step 3: Commit**

```bash
git add migrations/0001_metric_history.sql
git commit -m "feat(brief): add metric_history migration (applied manually)"
```

### Task 2.5 — `brief/headlines.py`: port the scraper

**Files:**
- Create: `brief/headlines.py`
- Test: `tests/test_headlines.py`

- [ ] **Step 1: Failing test**

`tests/test_headlines.py`:

```python
from unittest.mock import patch

from brief.headlines import HEADLINE_SOURCES, scrape_all, Headline


def test_sources_are_three():
    codes = [s["code"] for s in HEADLINE_SOURCES]
    assert codes == ["DS", "TBS", "FE"]


def test_scrape_all_returns_flat_list():
    ds_html = (
        '<a href="/business/one-long-title-here-about-economy">'
        'One long title here about economy</a>'
        '<a href="/business/two-long-title-here-about-markets">'
        'Two long title here about markets</a>'
    )

    def fake_fetch(url, _timeout=15):
        return ds_html if "thedailystar.net" in url else ""

    with patch("brief.headlines._fetch_page", side_effect=fake_fetch):
        result = scrape_all(count_per_source=2)

    assert all(isinstance(h, Headline) for h in result)
    titles = [h.title for h in result if h.source == "DS"]
    assert len(titles) == 2
    assert "about economy" in titles[0]


def test_scrape_all_tolerates_fetch_failure():
    with patch("brief.headlines._fetch_page", return_value=""):
        result = scrape_all(count_per_source=2)
    assert result == []
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/test_headlines.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/headlines.py` (port from `update.py` lines 43–111)**

```python
"""Headline scraping — ported verbatim from update.py:_scrape_headlines."""
from __future__ import annotations

import html as _html
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

HEADLINE_SOURCES: list[dict] = [
    {
        "url":     "https://www.thedailystar.net/business",
        "code":    "DS",
        "name":    "Daily Star",
        "pattern": r'<a\s+href="(/business/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>',
        "base":    "https://www.thedailystar.net",
    },
    {
        "url":     "https://www.tbsnews.net/economy",
        "code":    "TBS",
        "name":    "TBS News",
        "pattern": r'<a\s+href="(/economy/[^"]+)"[^>]*>\s*([^<]{15,}?)\s*</a>',
        "base":    "https://www.tbsnews.net",
    },
    {
        "url":     "https://today.thefinancialexpress.com.bd/",
        "code":    "FE",
        "name":    "Financial Express BD",
        "pattern": (
            r'<a\s+href="(https://today\.thefinancialexpress\.com\.bd/'
            r'(?:first-page|last-page|economy|stock-corporate|'
            r'trade-market|trade-commodities|public|national)/[^"]+)"'
            r'[^>]*>.*?<h4>([^<]+)</h4>'
        ),
        "base":    "",
        "dotall":  True,
    },
]


@dataclass(frozen=True)
class Headline:
    title: str
    url: str
    source: str
    published: datetime


def _fetch_page(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; TheBrief/1.0)"
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def scrape_source(src: dict, *, count: int = 4,
                  now: datetime | None = None) -> list[Headline]:
    now = now or datetime.now(timezone.utc)
    page = _fetch_page(src["url"])
    if not page:
        return []
    flags = re.IGNORECASE | (re.DOTALL if src.get("dotall") else 0)
    matches = re.findall(src["pattern"], page, flags)
    seen: set[str] = set()
    out: list[Headline] = []
    for path, raw_title in matches:
        title = re.sub(r'\s+', ' ', _html.unescape(raw_title)).strip()
        if len(title) < 20 or title.lower() in ("read more", "see all", "more news"):
            continue
        norm = re.sub(r'\s+', ' ', title.lower())
        if norm in seen:
            continue
        seen.add(norm)
        url = src["base"] + path if src["base"] else path
        out.append(Headline(title=title, url=url, source=src["code"], published=now))
        if len(out) >= count:
            break
    return out


def scrape_all(*, count_per_source: int = 4) -> list[Headline]:
    out: list[Headline] = []
    for src in HEADLINE_SOURCES:
        out.extend(scrape_source(src, count=count_per_source))
    return out
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_headlines.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add brief/headlines.py tests/test_headlines.py
git commit -m "feat(brief): port headline scraper from update.py"
```

### Task 2.6 — `BuilderContext`

**Files:**
- Modify: `brief/builders/__init__.py` (append)
- Test: add to existing `tests/builders/test_registry.py`

- [ ] **Step 1: Append the failing test**

```python
from datetime import date, datetime, timezone
from brief.builders import BuilderContext
from brief.econdelta import EconDeltaSnapshot


def _empty_snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={}, data={},
    )


def test_builder_context_holds_deps():
    ctx = BuilderContext(
        snapshot=_empty_snap(),
        history=None,
        today=date(2026, 4, 21),
        headlines=(),
        claude_outputs={},
    )
    assert ctx.today.year == 2026
    assert ctx.claude_outputs == {}
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/builders/test_registry.py -v`
Expected: FAIL (no BuilderContext).

- [ ] **Step 3: Append to `brief/builders/__init__.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Optional, Sequence

if TYPE_CHECKING:
    from brief.econdelta import EconDeltaSnapshot
    from brief.history import MetricHistoryClient
    from brief.headlines import Headline


@dataclass(frozen=True)
class BuilderContext:
    snapshot: "EconDeltaSnapshot"
    history: Optional["MetricHistoryClient"]
    today: date
    headlines: Sequence["Headline"] = ()
    claude_outputs: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/builders/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/builders/__init__.py tests/builders/test_registry.py
git commit -m "feat(brief): BuilderContext dataclass"
```

### Task 2.7 — Builder: `bb.py` (full TDD)

**Files:**
- Create: `brief/builders/bb.py`
- Test: `tests/builders/test_bb.py`

- [ ] **Step 1: Failing test**

`tests/builders/test_bb.py`:

```python
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from brief.builders import BuilderContext
from brief.builders.bb import build
from brief.econdelta import EconDeltaSnapshot
from brief.history import HistoryRow


def _snap(**overrides):
    data = {
        "gross_reserves_usd_bn": 34.1166,
        "reserves_date": "2026-04-14",
    }
    data.update(overrides)
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "ok", "age_hours": 0.1}},
        data=data,
    )


def test_bb_fresh_with_reserves_and_event_rates():
    history = MagicMock()
    history.get_latest.return_value = HistoryRow(
        "bb_gross_reserves", date(2026, 4, 13), 33.80, "BB"
    )
    ctx = BuilderContext(
        snapshot=_snap(),
        history=history,
        today=date(2026, 4, 21),
    )
    s = build(ctx)
    assert s.id == "bb"
    assert s.freshness in ("fresh", "warning")
    ids = {m.id for m in s.metrics}
    assert {"bb_policy_rate", "bb_sdf", "bb_gross_reserves"}.issubset(ids)
    reserves = next(m for m in s.metrics if m.id == "bb_gross_reserves")
    assert reserves.value == 34.1166
    assert reserves.delta is not None
    assert reserves.delta.direction == "up"
    assert reserves.delta.window == "wow"


def test_bb_handles_missing_reserves():
    ctx = BuilderContext(
        snapshot=_snap(gross_reserves_usd_bn=None),
        history=None,
        today=date(2026, 4, 21),
    )
    s = build(ctx)
    reserves = next((m for m in s.metrics if m.id == "bb_gross_reserves"), None)
    assert reserves is not None
    assert reserves.value is None
    assert s.freshness in ("unavailable", "warning", "stale")
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/builders/test_bb.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/builders/bb.py`**

```python
"""Builder: Policy & Rates (Bangladesh Bank).

Policy/SDF/SLF are event-cadence rates; reserves is weekly from EconDelta.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from brief.cadence import section_freshness
from brief.history import HistoryRow
from brief.schema import Delta, Metric, SectionData
from . import BuilderContext

# Event-cadence rates — source of truth is BB MPC. Updated via migration when MPC moves.
_POLICY_RATE_PCT = 10.0
_SDF_PCT = 8.5
_SLF_PCT = 11.5
_RATES_AS_OF = date(2026, 4, 18)   # latest MPC decision date; event-cadence


def _reserves_delta(current: float, history_row: HistoryRow | None) -> Delta | None:
    if history_row is None:
        return None
    try:
        prev = float(history_row.value)
    except (TypeError, ValueError):
        return None
    diff = round(current - prev, 4)
    return Delta(
        value=diff,
        direction="up" if diff > 0 else "down" if diff < 0 else "flat",
        window="wow",
    )


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = [
        Metric(id="bb_policy_rate", label="Policy Rate", value=_POLICY_RATE_PCT,
               unit="%", as_of=_RATES_AS_OF, source="BB",
               source_url="https://www.bb.org.bd/", cadence="event"),
        Metric(id="bb_sdf", label="SDF", value=_SDF_PCT,
               unit="%", as_of=_RATES_AS_OF, source="BB", cadence="event"),
        Metric(id="bb_slf", label="SLF", value=_SLF_PCT,
               unit="%", as_of=_RATES_AS_OF, source="BB", cadence="event"),
    ]

    reserves_val = ctx.snapshot.get("gross_reserves_usd_bn")
    reserves_as_of_str = ctx.snapshot.get("reserves_date")
    reserves_as_of = (
        date.fromisoformat(reserves_as_of_str) if reserves_as_of_str else ctx.today
    )

    prev = (
        ctx.history.get_latest("bb_gross_reserves")
        if (ctx.history is not None and reserves_val is not None)
        else None
    )

    reserves_metric = Metric(
        id="bb_gross_reserves",
        label="Gross Reserves",
        value=reserves_val,
        unit="bn USD",
        as_of=reserves_as_of,
        source="BB",
        source_url="https://www.bb.org.bd/",
        cadence="weekly",
        delta=_reserves_delta(reserves_val, prev) if reserves_val is not None else None,
    )
    metrics.append(reserves_metric)

    # Upsert fresh reserves into history for next run
    if ctx.history is not None and reserves_val is not None:
        ctx.history.upsert_many([
            HistoryRow("bb_gross_reserves", reserves_as_of, float(reserves_val), "BB"),
        ])

    freshness = section_freshness(metrics, today=ctx.today)
    return SectionData(
        id="bb",
        title="Policy & Rates (Bangladesh Bank)",
        metrics=metrics,
        freshness=freshness,
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/builders/test_bb.py -v`
Expected: PASS (2/2).

- [ ] **Step 5: Commit**

```bash
git add brief/builders/bb.py tests/builders/test_bb.py
git commit -m "feat(brief): bb builder (policy rates + reserves delta)"
```

### Task 2.8 — Builder: `fx.py` (full TDD)

**Files:**
- Create: `brief/builders/fx.py`
- Test: `tests/builders/test_fx.py`

- [ ] **Step 1: Failing test**

`tests/builders/test_fx.py`:

```python
from datetime import date, datetime, timezone

from brief.builders import BuilderContext
from brief.builders.fx import build
from brief.econdelta import EconDeltaSnapshot


def _snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "ok", "age_hours": 0.08}},
        data={
            "usd_bdt_mid": 122.70,
            "usd_bdt_buy": 122.60,
            "usd_bdt_sell": 122.80,
            "eur_bdt": 144.34,
            "gbp_bdt": 165.85,
        },
    )


def test_fx_fresh_populates_five_metrics():
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.id == "fx"
    ids = {m.id for m in s.metrics}
    assert ids == {"fx_usd_bdt_mid", "fx_usd_bdt_buy", "fx_usd_bdt_sell",
                   "fx_eur_bdt", "fx_gbp_bdt"}
    assert s.freshness == "fresh"


def test_fx_unavailable_when_bb_forex_stale():
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"bb_forex": {"status": "error", "age_hours": 72.0}},
        data={"usd_bdt_mid": None, "usd_bdt_buy": None, "usd_bdt_sell": None,
              "eur_bdt": None, "gbp_bdt": None},
    )
    ctx = BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.freshness == "unavailable"
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/builders/test_fx.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/builders/fx.py`**

```python
"""Builder: FX — daily rates from EconDelta bb_forex."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("fx_usd_bdt_mid",  "USD/BDT mid",  "usd_bdt_mid",  "BDT"),
    ("fx_usd_bdt_buy",  "USD/BDT buy",  "usd_bdt_buy",  "BDT"),
    ("fx_usd_bdt_sell", "USD/BDT sell", "usd_bdt_sell", "BDT"),
    ("fx_eur_bdt",      "EUR/BDT",      "eur_bdt",      "BDT"),
    ("fx_gbp_bdt",      "GBP/BDT",      "gbp_bdt",      "BDT"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics = [
        Metric(
            id=mid,
            label=label,
            value=ctx.snapshot.get(src_key),
            unit=unit,
            as_of=ctx.today,
            source="BB",
            source_url="https://www.bb.org.bd/en/index.php/econdata/exchangerate",
            cadence="daily",
        )
        for (mid, label, src_key, unit) in _SPEC
    ]
    return SectionData(
        id="fx",
        title="Foreign Exchange",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/builders/test_fx.py -v`
Expected: PASS (2/2).

- [ ] **Step 5: Commit**

```bash
git add brief/builders/fx.py tests/builders/test_fx.py
git commit -m "feat(brief): fx builder (5 daily metrics from bb_forex)"
```

### Task 2.9 — Builder: `dse.py` (full TDD)

**Files:**
- Create: `brief/builders/dse.py`
- Test: `tests/builders/test_dse.py`

- [ ] **Step 1: Failing test**

`tests/builders/test_dse.py`:

```python
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from brief.builders import BuilderContext
from brief.builders.dse import build
from brief.econdelta import EconDeltaSnapshot


def _snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "ok", "age_hours": 6.94}},
        data={
            "dsex": 5232.49, "dsex_change": -15.05, "dsex_change_pct": -0.29,
            "ds30": 1980.01, "dses": 1059.70, "turnover_crore": 824.76,
            "advancing": 120, "declining": 207, "unchanged": 62,
        },
    )


def test_dse_fresh_has_seven_metrics():
    ctx = BuilderContext(snapshot=_snap(), history=MagicMock(),
                         today=date(2026, 4, 21))
    ctx.history.get_latest.return_value = None
    s = build(ctx)
    assert s.id == "dse"
    ids = {m.id for m in s.metrics}
    assert {"dse_dsex_close", "dse_dsex_change_pct", "dse_ds30",
            "dse_dses", "dse_turnover_crore", "dse_advancing",
            "dse_declining"}.issubset(ids)


def test_dse_thursday_value_fresh_on_saturday():
    # Trading day closure on Thursday; Saturday run should still show fresh.
    ctx = BuilderContext(snapshot=_snap(), history=None, today=date(2026, 4, 18))
    s = build(ctx)
    dsex = next(m for m in s.metrics if m.id == "dse_dsex_close")
    assert dsex.value == 5232.49
    assert s.freshness in ("fresh", "warning")


def test_dse_unavailable_when_dsex_missing():
    snap = EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={"dse_market": {"status": "error"}},
        data={"dsex": None, "dsex_change": None, "dsex_change_pct": None,
              "ds30": None, "dses": None, "turnover_crore": None,
              "advancing": None, "declining": None, "unchanged": None},
    )
    ctx = BuilderContext(snapshot=snap, history=None, today=date(2026, 4, 21))
    s = build(ctx)
    assert s.freshness == "unavailable"
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/builders/test_dse.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/builders/dse.py`**

```python
"""Builder: DSE daily market snapshot."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.history import HistoryRow
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("dse_dsex_close",       "DSEX close",       "dsex",              "index"),
    ("dse_dsex_change_pct",  "DSEX %Δ",          "dsex_change_pct",   "%"),
    ("dse_ds30",             "DS30",             "ds30",              "index"),
    ("dse_dses",             "DSES",             "dses",              "index"),
    ("dse_turnover_crore",   "Turnover",         "turnover_crore",    "crore BDT"),
    ("dse_advancing",        "Advancing",        "advancing",         "stocks"),
    ("dse_declining",        "Declining",        "declining",         "stocks"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics = [
        Metric(
            id=mid,
            label=label,
            value=ctx.snapshot.get(src_key),
            unit=unit,
            as_of=ctx.today,
            source="DSE (via EconDelta)",
            source_url="https://www.dse.com.bd/market-statistics.php",
            cadence="daily",
        )
        for (mid, label, src_key, unit) in _SPEC
    ]

    # Upsert DSEX close for history + downstream chart delta
    dsex = ctx.snapshot.get("dsex")
    if ctx.history is not None and dsex is not None:
        ctx.history.upsert_many([
            HistoryRow("dse_dsex_close", ctx.today, float(dsex), "DSE"),
        ])

    return SectionData(
        id="dse",
        title="DSE Markets",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/builders/test_dse.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add brief/builders/dse.py tests/builders/test_dse.py
git commit -m "feat(brief): dse builder (DSEX + breadth from EconDelta)"
```

### Task 2.10 — Shared builders smoke fixture

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/builders/test_builders_smoke.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
"""Shared fixtures — use across builder/render tests."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot
from brief.builders import BuilderContext


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def fixture_snapshot() -> EconDeltaSnapshot:
    payload = json.loads((FIXTURES / "econdelta_latest.json").read_text())
    return EconDeltaSnapshot(
        updated_at=datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00")),
        sources_status=payload["sources_status"],
        data=payload["data"],
    )


@pytest.fixture
def today() -> date:
    return date(2026, 4, 21)


@pytest.fixture
def ctx(fixture_snapshot, today) -> BuilderContext:
    return BuilderContext(
        snapshot=fixture_snapshot,
        history=None,
        today=today,
    )
```

- [ ] **Step 2: Write smoke test matrix (all 14 builders)**

`tests/builders/test_builders_smoke.py`:

```python
"""Smoke test: every builder produces a valid SectionData from the fixture."""
from __future__ import annotations

import importlib
import pytest

from brief.builders import ALL_BUILDER_IDS
from brief.schema import SectionData


@pytest.mark.parametrize("bid", ALL_BUILDER_IDS)
def test_builder_smokes(bid, ctx):
    # Late-phase builders (headlines, exec) skip in Phase 2; they light up in Phase 3.
    try:
        mod = importlib.import_module(f"brief.builders.{bid}")
    except ModuleNotFoundError:
        pytest.skip(f"builder {bid} not yet implemented")

    section = mod.build(ctx)
    assert isinstance(section, SectionData)
    assert section.id == {
        "bb": "bb", "macro": "macro", "fx": "fx", "remit": "remit",
        "dse": "dse", "tbond": "tbond", "iranwar": "iranwar",
        "headlines": "headlines", "exec": "exec",
        "comm": "comm", "banking": "banking",
        "dam": "dam", "fiscal": "fiscal", "nbr": "nbr",
    }[bid]
    assert section.freshness in (
        "fresh", "warning", "stale", "pending", "unavailable"
    )
```

- [ ] **Step 3: Run — expect most skipped, bb/fx/dse pass**

Run: `pytest tests/builders/test_builders_smoke.py -v`
Expected: 3 pass, 11 skipped.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/builders/test_builders_smoke.py
git commit -m "test(brief): shared ctx fixture + builder smoke matrix"
```

### Task 2.11 — Builder: `macro.py`

**Files:**
- Create: `brief/builders/macro.py`

- [ ] **Step 1: Write implementation**

`brief/builders/macro.py`:

```python
"""Builder: Macro (CPI + MPC). Monthly cadence; no EconDelta source today.

Initial release reads last-known from metric_history only. Values land as None
until an EconDelta or dedicated scraper populates them.
"""
from __future__ import annotations

from datetime import date

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_HIST_SPEC = (
    ("macro_cpi_headline", "CPI Headline", "%",       "BBS", "monthly"),
    ("macro_cpi_food",     "CPI Food",     "%",       "BBS", "monthly"),
    ("macro_gdp_growth",   "GDP Growth",   "%",       "BBS", "quarterly"),
    ("macro_credit_growth","Credit Growth","% YoY",   "BB",  "monthly"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source, cadence in _HIST_SPEC:
        last = ctx.history.get_latest(mid) if ctx.history is not None else None
        value = last.value if last is not None else None
        as_of = last.as_of if last is not None else ctx.today
        metrics.append(Metric(
            id=mid, label=label, value=value, unit=unit,
            as_of=as_of, source=source, cadence=cadence,  # type: ignore[arg-type]
        ))

    return SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke — expect macro now passes**

Run: `pytest tests/builders/test_builders_smoke.py -v -k macro`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/macro.py
git commit -m "feat(brief): macro builder (CPI/GDP from history)"
```

### Task 2.12 — Builder: `remit.py` (Remittance)

**Files:**
- Create: `brief/builders/remit.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Remittance — monthly cadence; last-known from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    last_mn = ctx.history.get_latest("remit_monthly_mn") if ctx.history else None
    last_yoy = ctx.history.get_latest("remit_yoy_pct") if ctx.history else None

    metrics = [
        Metric(
            id="remit_monthly_mn", label="Monthly Remittance",
            value=(last_mn.value if last_mn else None), unit="mn USD",
            as_of=(last_mn.as_of if last_mn else ctx.today),
            source="BB (publictn/5/27)", cadence="monthly",
        ),
        Metric(
            id="remit_yoy_pct", label="YoY %", value=(last_yoy.value if last_yoy else None),
            unit="%", as_of=(last_yoy.as_of if last_yoy else ctx.today),
            source="BB", cadence="monthly",
        ),
    ]
    return SectionData(
        id="remit", title="Remittance", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke — expect remit passes**

Run: `pytest tests/builders/test_builders_smoke.py -v -k remit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/remit.py
git commit -m "feat(brief): remit builder (monthly last-known)"
```

### Task 2.13 — Builder: `tbond.py`

**Files:**
- Create: `brief/builders/tbond.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: T-Bill / T-Bond — event-cadence yields, history-driven."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_METRIC_SPEC = (
    ("tbond_tbill_91d",   "91d T-Bill cut-off",  "%",   "BB", "event"),
    ("tbond_tbill_182d",  "182d T-Bill cut-off", "%",   "BB", "event"),
    ("tbond_tbill_364d",  "364d T-Bill cut-off", "%",   "BB", "event"),
    ("tbond_bond_5y",     "5y Govt Bond",        "%",   "BB", "weekly"),
    ("tbond_bond_10y",    "10y Govt Bond",       "%",   "BB", "weekly"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source, cadence in _METRIC_SPEC:
        last = ctx.history.get_latest(mid) if ctx.history else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence=cadence,  # type: ignore[arg-type]
        ))
    return SectionData(
        id="tbond", title="T-Bonds & T-Bills", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — Expect PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/tbond.py
git commit -m "feat(brief): tbond builder (5 yield metrics from history)"
```

### Task 2.14 — Builder: `iranwar.py`

**Files:**
- Create: `brief/builders/iranwar.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Iran War / Oil — daily commodity prices from EconDelta + BankerRead-worthy."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    src = "EconDelta commodity_prices"
    metrics = [
        Metric(id="iranwar_brent_spot", label="Brent spot",
               value=ctx.snapshot.get("brent_crude_usd_barrel"),
               unit="USD/bbl", as_of=ctx.today, source=src, cadence="daily"),
        Metric(id="iranwar_wti_spot", label="WTI spot",
               value=ctx.snapshot.get("wti_crude_usd_barrel"),
               unit="USD/bbl", as_of=ctx.today, source=src, cadence="daily"),
    ]
    return SectionData(
        id="iranwar", title="Iran War & Oil", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/iranwar.py
git commit -m "feat(brief): iranwar builder (Brent/WTI daily)"
```

### Task 2.15 — Builder: `comm.py` (Commodities)

**Files:**
- Create: `brief/builders/comm.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Commodities — gold (from EconDelta), LNG (from history)."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    gold_oz = ctx.snapshot.get("gold_usd_oz")

    last_lng = ctx.history.get_latest("comm_lng_jkm") if ctx.history else None
    last_gold_bdt = ctx.history.get_latest("comm_gold_22k_bdt") if ctx.history else None

    metrics = [
        Metric(id="comm_gold_usd_oz", label="Gold", value=gold_oz,
               unit="USD/oz", as_of=ctx.today, source="EconDelta", cadence="daily"),
        Metric(id="comm_gold_22k_bdt", label="Gold 22K",
               value=(last_gold_bdt.value if last_gold_bdt else None),
               unit="BDT/bhori",
               as_of=(last_gold_bdt.as_of if last_gold_bdt else ctx.today),
               source="BAJUS", cadence="daily"),
        Metric(id="comm_lng_jkm", label="LNG JKM",
               value=(last_lng.value if last_lng else None),
               unit="USD/MMBtu",
               as_of=(last_lng.as_of if last_lng else ctx.today),
               source="History", cadence="weekly"),
    ]
    return SectionData(
        id="comm", title="Commodities", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/comm.py
git commit -m "feat(brief): comm builder (gold daily + LNG history)"
```

### Task 2.16 — Builder: `banking.py`

**Files:**
- Create: `brief/builders/banking.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Banking — quarterly NPL / CAR from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    last_npl = ctx.history.get_latest("banking_npl_pct") if ctx.history else None
    last_car = ctx.history.get_latest("banking_car_pct") if ctx.history else None
    metrics = [
        Metric(id="banking_npl_pct", label="NPL Ratio",
               value=(last_npl.value if last_npl else None), unit="%",
               as_of=(last_npl.as_of if last_npl else ctx.today),
               source="BB", cadence="quarterly"),
        Metric(id="banking_car_pct", label="CAR",
               value=(last_car.value if last_car else None), unit="%",
               as_of=(last_car.as_of if last_car else ctx.today),
               source="BB", cadence="quarterly"),
    ]
    return SectionData(
        id="banking", title="Banking", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/banking.py
git commit -m "feat(brief): banking builder (NPL/CAR quarterly)"
```

### Task 2.17 — Builder: `dam.py`

**Files:**
- Create: `brief/builders/dam.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: DAM weekly food prices — history-backed; scraper lands in a follow-up PR."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_ITEMS = (
    ("dam_rice_coarse",   "Rice (coarse)", "BDT/kg"),
    ("dam_rice_fine",     "Rice (fine)",   "BDT/kg"),
    ("dam_lentil",        "Red lentil",    "BDT/kg"),
    ("dam_oil",           "Soybean oil",   "BDT/L"),
    ("dam_sugar",         "Sugar",         "BDT/kg"),
    ("dam_onion",         "Onion",         "BDT/kg"),
    ("dam_egg",           "Egg",           "BDT/doz"),
    ("dam_chicken",       "Broiler",       "BDT/kg"),
    ("dam_flour",         "Wheat flour",   "BDT/kg"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit in _ITEMS:
        last = ctx.history.get_latest(mid) if ctx.history else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source="DAM Bangladesh", cadence="weekly",
        ))
    return SectionData(
        id="dam", title="DAM Food Prices", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/dam.py
git commit -m "feat(brief): dam builder (9 weekly food prices)"
```

### Task 2.18 — Builder: `fiscal.py`

**Files:**
- Create: `brief/builders/fiscal.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Fiscal — monthly NBR / ADP / borrow from history."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("fiscal_nbr_collected_trn", "NBR collected YTD", "BDT trn", "NBR"),
    ("fiscal_nbr_target_trn",    "NBR full-year target", "BDT trn", "NBR"),
    ("fiscal_adp_pct",           "ADP utilisation", "%",  "IMED"),
    ("fiscal_govt_borrow_trn",   "Govt bank borrow YTD", "BDT trn", "BB"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source in _SPEC:
        last = ctx.history.get_latest(mid) if ctx.history else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence="monthly",
        ))
    return SectionData(
        id="fiscal", title="Fiscal", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/fiscal.py
git commit -m "feat(brief): fiscal builder (NBR/ADP/borrow monthly)"
```

### Task 2.19 — Builder: `nbr.py`

**Files:**
- Create: `brief/builders/nbr.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: NBR revenue composition — monthly last-known."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("nbr_vat_bn",     "VAT",     "BDT bn", "NBR"),
    ("nbr_it_bn",      "Income Tax", "BDT bn", "NBR"),
    ("nbr_customs_bn", "Customs", "BDT bn", "NBR"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source in _SPEC:
        last = ctx.history.get_latest(mid) if ctx.history else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence="monthly",
        ))
    return SectionData(
        id="nbr", title="NBR Revenue", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/nbr.py
git commit -m "feat(brief): nbr builder (VAT/IT/customs monthly)"
```

### Task 2.20 — Builder: `headlines.py`

**Files:**
- Create: `brief/builders/headlines.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Headlines — takes raw scraped list + optional curation from Claude Call 1.

Fresh path: use curation from `ctx.claude_outputs['headlines_curation']['selected']`
to keep only selected URLs (in order). Fail-closed: show all scraped headlines.
"""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, NewsItem, SectionData
from . import BuilderContext


def _news_items(ctx: BuilderContext) -> list[NewsItem]:
    items = [
        NewsItem(title=h.title, url=h.url, source=h.source, published=h.published)
        for h in ctx.headlines
    ]
    curation = ctx.claude_outputs.get("headlines_curation") if ctx.claude_outputs else None
    if not curation or not isinstance(curation, dict):
        return items
    selected_urls = [s.get("url") for s in curation.get("selected", []) if s.get("url")]
    if not selected_urls:
        return items
    by_url = {n.url: n for n in items}
    return [by_url[u] for u in selected_urls if u in by_url]


def build(ctx: BuilderContext) -> SectionData:
    news = _news_items(ctx)
    count_metric = Metric(
        id="headlines_count", label="Headlines count",
        value=len(news), unit="items", as_of=ctx.today,
        source="scraper", cadence="daily",
    )
    return SectionData(
        id="headlines", title="Headlines",
        metrics=[count_metric], news=news,
        freshness=section_freshness([count_metric], today=ctx.today),
    )
```

- [ ] **Step 2: Run smoke** — PASS (count=0, freshness=fresh for daily with value=0).

- [ ] **Step 3: Commit**

```bash
git add brief/builders/headlines.py
git commit -m "feat(brief): headlines builder (scraped + Claude curation)"
```

### Task 2.21 — Builder: `exec.py`

**Files:**
- Create: `brief/builders/exec.py`

- [ ] **Step 1: Write implementation**

```python
"""Builder: Executive Signals — consumes Claude Call 2 output.

Phase 2 stub: produces empty SectionData so the smoke matrix passes; the
real exec_signals list is injected in Phase 3 via ctx.claude_outputs.
"""
from __future__ import annotations

from brief.schema import ExecSignal, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    raw = (ctx.claude_outputs or {}).get("exec_signals") or {}
    signals_payload = raw.get("signals", []) if isinstance(raw, dict) else []
    signals: list[ExecSignal] = []
    for s in signals_payload:
        try:
            signals.append(ExecSignal(
                direction=s["direction"],
                text=s["text"],
                section_anchor=s["section_anchor"],
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return SectionData(
        id="exec",
        title="Executive Signals",
        freshness="fresh" if signals else "pending",
        exec_signals=signals or None,
    )
```

- [ ] **Step 2: Run smoke** — PASS.

- [ ] **Step 3: Commit**

```bash
git add brief/builders/exec.py
git commit -m "feat(brief): exec builder (stub: consumes Claude Call 2)"
```

### Task 2.22 — `brief/pipeline.py`: `gather()`

**Files:**
- Create: `brief/pipeline.py`
- Test: `tests/test_pipeline_integration.py`

- [ ] **Step 1: Failing integration test**

`tests/test_pipeline_integration.py`:

```python
from datetime import date
import pytest

from brief.pipeline import gather, PipelineConfig
from brief.schema import SectionData


@pytest.mark.integration
def test_gather_returns_14_sections(fixture_snapshot, today):
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)
    assert len(sections) == 14
    ids = [s.id for s in sections]
    assert ids == [
        "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
        "headlines", "exec",
        "comm", "banking", "dam", "fiscal", "nbr",
    ]
    for s in sections:
        assert isinstance(s, SectionData)
        assert s.freshness in ("fresh", "warning", "stale", "pending", "unavailable")
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/test_pipeline_integration.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/pipeline.py`**

```python
"""Pipeline orchestrator — Phase 2 version (no Claude wiring yet).

Phase 3 will extend gather() with 3 Claude calls; Phase 4 adds render().
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

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
            sections.append(SectionData(
                id=bid,
                title=bid.upper(),
                freshness="unavailable",
                freshness_reason=f"builder error: {type(e).__name__}: {e}",
            ))
    return sections
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_pipeline_integration.py -v`
Expected: PASS (1/1).

- [ ] **Step 5: Commit**

```bash
git add brief/pipeline.py tests/test_pipeline_integration.py
git commit -m "feat(brief): pipeline.gather orchestrator (Phase 2 shape)"
```

### Task 2.23 — Phase 2 exit gate

- [ ] **Step 1: Full test run**

Run: `pytest`
Expected: all PASS, coverage ≥80%.

- [ ] **Step 2: Dry-run against live EconDelta (dev box)**

Optional sanity check on the Mac: point `ECONDELTA_DATA` at the fixture and invoke gather manually.

```bash
ECONDELTA_DATA=$PWD/fixtures/econdelta_latest.json \
  python -c "from brief.pipeline import gather, PipelineConfig; \
             ss = gather(PipelineConfig(enable_history=False, enable_headlines=False)); \
             print([(s.id, s.freshness) for s in ss])"
```

Expected: list of 14 `(id, freshness)` tuples.

- [ ] **Step 3: Phase 2 marker commit (optional)**

```bash
git commit --allow-empty -m "chore(brief): Phase 2 builders complete"
```

---

## Phase 3 — Claude integration (~3h)

Wire the three Max CLI calls. Subprocess-only, no Anthropic API. Each call has a prompt file, a validator, and a fail-closed fallback.

### Task 3.1 — `brief/claude/max_client.py`: subprocess wrapper

**Files:**
- Create: `brief/claude/max_client.py`
- Test: `tests/claude/test_max_client.py`

- [ ] **Step 1: Failing test**

`tests/claude/test_max_client.py`:

```python
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from brief.claude.max_client import (
    MaxCallError, MaxCallResult, run_max,
)


def _fake_completed(stdout: str, returncode: int = 0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = ""
    return m


def test_run_max_returns_parsed_json():
    claude_payload = {
        "result": json.dumps({"selected": [], "rationale_bullet": "x"}),
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "total_cost_usd": 0.01,
    }
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps(claude_payload))):
        r = run_max(prompt="hi", timeout_s=60)

    assert isinstance(r, MaxCallResult)
    assert r.parsed == {"selected": [], "rationale_bullet": "x"}
    assert r.usage == {"input_tokens": 10, "output_tokens": 5}
    assert r.raw_text == json.dumps({"selected": [], "rationale_bullet": "x"})


def test_run_max_rejects_bad_returncode():
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed("", returncode=1)):
        with pytest.raises(MaxCallError):
            run_max(prompt="hi", timeout_s=60)


def test_run_max_rejects_non_json_outer():
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed("not json")):
        with pytest.raises(MaxCallError):
            run_max(prompt="hi", timeout_s=60)


def test_run_max_returns_raw_text_when_result_is_not_json():
    with patch("brief.claude.max_client.subprocess.run",
               return_value=_fake_completed(json.dumps({
                   "result": "plain text not json",
                   "usage": {},
               }))):
        r = run_max(prompt="hi", timeout_s=60)
    assert r.parsed is None
    assert r.raw_text == "plain text not json"


def test_run_max_wraps_timeout():
    with patch("brief.claude.max_client.subprocess.run",
               side_effect=subprocess.TimeoutExpired("claude", 60)):
        with pytest.raises(MaxCallError):
            run_max(prompt="hi", timeout_s=60)
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/claude/test_max_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/claude/max_client.py`**

```python
"""Subprocess wrapper around the `claude -p` Max CLI.

No Anthropic API calls. Auth is via the OS user's ~/.claude/.credentials.json
(Max OAuth), injected by the CLI itself — we pass no tokens.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


class MaxCallError(RuntimeError):
    """Raised when the CLI fails, times out, or returns non-JSON."""


@dataclass(frozen=True)
class MaxCallResult:
    raw_text: str        # Claude's `result` field as a string
    parsed: Any | None   # json.loads(raw_text) or None if result wasn't JSON
    usage: dict[str, Any]
    total_cost_usd: float | None


def run_max(
    *,
    prompt: str,
    model: str = "claude-opus-4-7",
    timeout_s: int = 1800,
    claude_binary: str = "claude",
) -> MaxCallResult:
    """Invoke the Claude Max CLI, return parsed result."""
    argv = [
        claude_binary, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--tools", "",
        "--permission-mode", "bypassPermissions",
    ]
    try:
        cp = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise MaxCallError(f"Claude CLI timed out after {timeout_s}s") from e
    except FileNotFoundError as e:
        raise MaxCallError(f"Claude CLI binary not found: {claude_binary}") from e

    if cp.returncode != 0:
        raise MaxCallError(
            f"Claude CLI exited {cp.returncode}: {cp.stderr.strip()[:500]}"
        )

    try:
        outer = json.loads(cp.stdout)
    except json.JSONDecodeError as e:
        raise MaxCallError(f"Claude CLI stdout is not JSON: {e}") from e

    raw_text = outer.get("result", "")
    if not isinstance(raw_text, str):
        raise MaxCallError("Claude CLI returned non-string result field")

    parsed: Any | None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None

    return MaxCallResult(
        raw_text=raw_text,
        parsed=parsed,
        usage=outer.get("usage") or {},
        total_cost_usd=outer.get("total_cost_usd"),
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/claude/test_max_client.py -v`
Expected: PASS (5/5).

- [ ] **Step 5: Commit**

```bash
git add brief/claude/max_client.py tests/claude/test_max_client.py
git commit -m "feat(brief): max_client subprocess wrapper with timeout"
```

### Task 3.2 — Prompt: `headlines_curation.txt`

**Files:**
- Create: `brief/claude/prompts/headlines_curation.txt`

- [ ] **Step 1: Write the prompt**

```text
You curate a banker's daily headline set. Return JSON only — no markdown, no prose.

INPUT: a list of up to 30 headlines from Bangladesh / global business wire feeds.
Each item has {title, url, source, published}.

YOUR JOB:
1. Select the 8–15 most relevant headlines for a Bangladesh senior banker (CFO, CRO,
   Head of SME, Treasury) to read before market open.
2. Classify each by domain — one of:
   banking, markets, fx, commodities, policy, geopolitics, headline-only.
3. Assign a weight — "high" | "med" | "low".
4. Write ONE editorial sentence summarising the day's signal.

RULES:
- Never invent a title or URL. Use only items you are given.
- Every selected URL must match a URL in the input set byte-for-byte.
- Prefer domain diversity over dogpiling one story.

OUTPUT SCHEMA (strict JSON):
{"selected":[{"url":"…","domain":"fx","weight":"high"}, …],
 "rationale_bullet":"one short editorial sentence"}

HEADLINES:
{{HEADLINES_JSON}}
```

- [ ] **Step 2: Commit**

```bash
git add brief/claude/prompts/headlines_curation.txt
git commit -m "feat(brief): headlines_curation prompt"
```

### Task 3.3 — Prompt: `exec_signals.txt`

**Files:**
- Create: `brief/claude/prompts/exec_signals.txt`

- [ ] **Step 1: Write the prompt**

```text
You write a senior banker's one-liner summary of today's Bangladesh signals.
Return JSON only.

INPUT: a list of SectionData objects with metrics, freshness, and deltas. Plus today's date.
No raw HTML, no raw news text. You have ONLY the metrics listed.

YOUR JOB:
- Produce 6–8 signals.
- Each signal: {direction, text, section_anchor}.
- `direction` ∈ {bull, bear, warn, watch}.
- `text` ≤ 15 words. Must reference a specific metric + direction from the input.
- `section_anchor` must equal one of these section ids: bb, macro, fx, remit, dse,
  tbond, iranwar, headlines, comm, banking, dam, fiscal, nbr.

Also emit one `traffic_status` — one of bull, bear, warn, neu.

RULES:
- No hedging, no "monitor closely". Specific numbers / thresholds only.
- Do NOT cite a metric whose freshness is "unavailable".

OUTPUT SCHEMA (strict JSON):
{"signals":[{"direction":"bull","text":"…","section_anchor":"bb"}, …],
 "traffic_status":"neu"}

TODAY: {{TODAY_ISO}}
SECTIONS:
{{SECTIONS_JSON}}
```

- [ ] **Step 2: Commit**

```bash
git add brief/claude/prompts/exec_signals.txt
git commit -m "feat(brief): exec_signals prompt"
```

### Task 3.4 — Prompts: `bankerread.txt` + stale variant

**Files:**
- Create: `brief/claude/prompts/bankerread.txt`
- Create: `brief/claude/prompts/bankerread_stale.txt`

- [ ] **Step 1: Write `bankerread.txt`**

```text
You write "Banker Read" insights — one 4-sentence insight per section — for
Bangladesh senior bankers. Return JSON only.

INPUT: all spine SectionData + today's exec_signals.
TODAY: {{TODAY_ISO}}

PER SECTION — structure each 4-sentence insight as:
(1) What today's data means for the book.
(2) A named action with exposure type or threshold.
(3) A trigger to watch with metric + threshold.
(4) Strategic focus.

RULES:
- Cite actual numbers from the input. Never generic phrases.
- No double quotes inside any sentence (breaks JSX). Use single quotes.
- 4 sentences per section, exactly. No more, no less.

OUTPUT SCHEMA:
{"insights":{"bb":["s1","s2","s3","s4"], "fx":["s1","s2","s3","s4"], …}}

Only include section ids whose freshness is "fresh" or "warning".

SECTIONS (fresh/warning only):
{{SECTIONS_JSON}}
EXEC_SIGNALS:
{{EXEC_SIGNALS_JSON}}
```

- [ ] **Step 2: Write `bankerread_stale.txt`**

```text
You write a single sentence per STALE section — a news-driven micro-summary
for a Bangladesh senior banker. Return JSON only.

INPUT: a list of stale section ids, with the headline set from today.
TODAY: {{TODAY_ISO}}

PER SECTION:
- One sentence. Start with "No fresh data; " if literally true.
- Otherwise reference a specific headline URL from the input.
- ≤ 25 words. No double quotes inside.

OUTPUT SCHEMA:
{"insights":{"bb":["…"], "remit":["…"], …}}

STALE_SECTIONS:
{{STALE_SECTIONS_JSON}}
HEADLINES:
{{HEADLINES_JSON}}
```

- [ ] **Step 3: Commit**

```bash
git add brief/claude/prompts/bankerread.txt brief/claude/prompts/bankerread_stale.txt
git commit -m "feat(brief): bankerread prompts (full + stale variant)"
```

### Task 3.5 — `brief/claude/validators.py`

**Files:**
- Create: `brief/claude/validators.py`
- Test: `tests/claude/test_validators.py`

- [ ] **Step 1: Failing test**

`tests/claude/test_validators.py`:

```python
from brief.claude.validators import (
    validate_curation, validate_signals, validate_insights,
    ValidationResult,
)


def test_curation_valid():
    payload = {"selected": [{"url": "u1", "domain": "fx", "weight": "high"},
                            {"url": "u2", "domain": "banking", "weight": "med"}],
               "rationale_bullet": "mixed signal day"}
    r = validate_curation(payload, allowed_urls={"u1", "u2", "u3"})
    assert r.ok is True
    assert r.value == payload


def test_curation_rejects_unknown_url():
    payload = {"selected": [{"url": "INVENTED", "domain": "fx", "weight": "high"}],
               "rationale_bullet": "x"}
    r = validate_curation(payload, allowed_urls={"u1"})
    assert r.ok is False


def test_curation_rejects_bad_weight():
    payload = {"selected": [{"url": "u1", "domain": "fx", "weight": "HUGE"}],
               "rationale_bullet": "x"}
    r = validate_curation(payload, allowed_urls={"u1"})
    assert r.ok is False


def test_signals_valid():
    payload = {"signals": [
        {"direction": "bull", "text": "Reserves up", "section_anchor": "bb"},
    ], "traffic_status": "neu"}
    r = validate_signals(payload, allowed_anchors={"bb", "fx"})
    assert r.ok is True


def test_signals_rejects_bad_anchor():
    payload = {"signals": [{"direction": "bull", "text": "x",
                            "section_anchor": "nope"}],
               "traffic_status": "neu"}
    r = validate_signals(payload, allowed_anchors={"bb"})
    assert r.ok is False


def test_signals_rejects_too_long_text():
    long = " ".join(["word"] * 30)
    payload = {"signals": [{"direction": "bull", "text": long,
                            "section_anchor": "bb"}],
               "traffic_status": "neu"}
    r = validate_signals(payload, allowed_anchors={"bb"})
    assert r.ok is False


def test_insights_full_requires_four_sentences():
    payload = {"insights": {"bb": ["a", "b", "c", "d"],
                            "fx": ["a", "b", "c"]}}
    r = validate_insights(payload, allowed_section_ids={"bb", "fx"}, stale=False)
    assert r.ok is True
    assert set(r.value["insights"].keys()) == {"bb"}
    assert "fx" in r.dropped


def test_insights_stale_requires_one_sentence():
    payload = {"insights": {"remit": ["no fresh data; x"]}}
    r = validate_insights(payload, allowed_section_ids={"remit"}, stale=True)
    assert r.ok is True


def test_insights_rejects_double_quotes():
    payload = {"insights": {"bb": ['has "bad" quotes', "b", "c", "d"]}}
    r = validate_insights(payload, allowed_section_ids={"bb"}, stale=False)
    assert r.ok is True
    assert "bb" in r.dropped  # dropped for invalid quotes
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/claude/test_validators.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/claude/validators.py`**

```python
"""Validators for the three Claude calls. Each returns a ValidationResult.

Contract: validator never raises. On malformed input it sets ok=False and
returns a reason. On partial validity (insights), ok=True but invalid
per-section entries are moved to `dropped` so the caller can fall back
per section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

_VALID_WEIGHTS = {"high", "med", "low"}
_VALID_DIRECTIONS = {"bull", "bear", "warn", "watch"}
_VALID_TRAFFIC = {"bull", "bear", "warn", "neu"}


@dataclass
class ValidationResult:
    ok: bool
    value: Any = None
    reason: str = ""
    dropped: dict[str, str] = field(default_factory=dict)


def _is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def validate_curation(payload: Any, *, allowed_urls: set[str]) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    selected = payload.get("selected")
    if not isinstance(selected, list) or not (8 <= len(selected) <= 15):
        # spec says 8-15, but tolerate smaller sets in case headline pool is thin
        if not isinstance(selected, list) or not (1 <= len(selected) <= 20):
            return ValidationResult(False, reason="selected size out of range")

    for item in selected:
        if not _is_dict(item):
            return ValidationResult(False, reason="selected item not a dict")
        url = item.get("url")
        weight = item.get("weight")
        if url not in allowed_urls:
            return ValidationResult(False, reason=f"unknown url: {url!r}")
        if weight not in _VALID_WEIGHTS:
            return ValidationResult(False, reason=f"bad weight: {weight!r}")
    if not isinstance(payload.get("rationale_bullet"), str):
        return ValidationResult(False, reason="rationale_bullet not a string")
    return ValidationResult(True, value=payload)


def validate_signals(payload: Any, *, allowed_anchors: set[str]) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    signals = payload.get("signals")
    if not isinstance(signals, list) or not signals:
        return ValidationResult(False, reason="no signals")
    for s in signals:
        if not _is_dict(s):
            return ValidationResult(False, reason="signal not a dict")
        if s.get("direction") not in _VALID_DIRECTIONS:
            return ValidationResult(False, reason=f"bad direction: {s.get('direction')!r}")
        if s.get("section_anchor") not in allowed_anchors:
            return ValidationResult(False, reason=f"bad anchor: {s.get('section_anchor')!r}")
        text = s.get("text")
        if not isinstance(text, str) or len(text.split()) > 20:
            return ValidationResult(False, reason="text too long or missing")
    if payload.get("traffic_status") not in _VALID_TRAFFIC:
        return ValidationResult(False, reason=f"bad traffic_status: {payload.get('traffic_status')!r}")
    return ValidationResult(True, value=payload)


def validate_insights(
    payload: Any, *, allowed_section_ids: Iterable[str], stale: bool,
) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    insights = payload.get("insights")
    if not _is_dict(insights):
        return ValidationResult(False, reason="insights not a dict")

    expected_len = 1 if stale else 4
    allowed = set(allowed_section_ids)
    kept: dict[str, list[str]] = {}
    dropped: dict[str, str] = {}

    for sid, sentences in insights.items():
        if sid not in allowed:
            dropped[sid] = "section not in allowed set"
            continue
        if not isinstance(sentences, list) or len(sentences) != expected_len:
            dropped[sid] = f"wrong sentence count (need {expected_len})"
            continue
        if not all(isinstance(s, str) for s in sentences):
            dropped[sid] = "non-string sentence"
            continue
        if any('"' in s for s in sentences):
            dropped[sid] = "contains double quote (JSX-breaking)"
            continue
        kept[sid] = list(sentences)

    return ValidationResult(
        ok=True,
        value={"insights": kept},
        dropped=dropped,
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/claude/test_validators.py -v`
Expected: PASS (9/9).

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/claude/test_validators.py
git commit -m "feat(brief): Claude response validators (3 calls + stale variant)"
```

### Task 3.6 — Pipeline wiring: 3 Claude calls

**Files:**
- Modify: `brief/pipeline.py`
- Modify: `tests/test_pipeline_integration.py` (add a mocked-Claude test)

- [ ] **Step 1: Append a failing test**

Append to `tests/test_pipeline_integration.py`:

```python
from unittest.mock import patch

from brief.claude.max_client import MaxCallResult
from brief.pipeline import run_pipeline


def _fake_curation(urls):
    return MaxCallResult(
        raw_text="{}",
        parsed={"selected": [{"url": u, "domain": "fx", "weight": "med"} for u in urls[:2]],
                "rationale_bullet": "test"},
        usage={}, total_cost_usd=0,
    )


def _fake_signals():
    return MaxCallResult(
        raw_text="{}",
        parsed={"signals": [{"direction": "bull", "text": "reserves up",
                             "section_anchor": "bb"}],
                "traffic_status": "neu"},
        usage={}, total_cost_usd=0,
    )


def _fake_insights():
    return MaxCallResult(
        raw_text="{}",
        parsed={"insights": {"bb": ["one", "two", "three", "four"],
                             "fx": ["one", "two", "three", "four"]}},
        usage={}, total_cost_usd=0,
    )


def test_run_pipeline_injects_claude_outputs(fixture_snapshot, today):
    from brief.pipeline import PipelineConfig

    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)

    call_count = {"n": 0}
    responses = [_fake_curation([]), _fake_signals(), _fake_insights()]

    def _stub(**kwargs):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r

    with patch("brief.pipeline.run_max", side_effect=_stub):
        result = run_pipeline(cfg, snapshot_override=fixture_snapshot)

    assert call_count["n"] == 3
    exec_section = next(s for s in result.sections if s.id == "exec")
    assert exec_section.exec_signals is not None
    assert len(exec_section.exec_signals) >= 1

    bb = next(s for s in result.sections if s.id == "bb")
    assert bb.bankerread is not None
    assert bb.bankerread.variant == "full"
```

- [ ] **Step 2: Run — FAIL (run_pipeline missing)**

Run: `pytest tests/test_pipeline_integration.py -v -k run_pipeline`
Expected: FAIL.

- [ ] **Step 3: Extend `brief/pipeline.py`**

Append to `brief/pipeline.py`:

```python
from dataclasses import dataclass as _dc
from datetime import datetime, timezone

from brief.builders import SPINE_BUILDER_IDS, ALL_BUILDER_IDS
from brief.claude.max_client import MaxCallError, MaxCallResult, run_max
from brief.claude.validators import (
    ValidationResult,
    validate_curation,
    validate_insights,
    validate_signals,
)
from brief.schema import BankerReadInsight


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
        if full_sentences:
            s.bankerread = BankerReadInsight(
                sentences=full_sentences, generated_at=now, variant="full",
            )
            continue
        stale_sentences = insights_stale.get(s.id)
        if stale_sentences:
            s.bankerread = BankerReadInsight(
                sentences=stale_sentences, generated_at=now, variant="stale_micro",
            )

    return PipelineResult(
        sections=sections_v2,
        claude_outputs=claude_outputs,
        call_reports=call_reports,
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_pipeline_integration.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add brief/pipeline.py tests/test_pipeline_integration.py
git commit -m "feat(brief): pipeline wires 3 Claude calls + fallbacks"
```

### Task 3.7 — VPS dry-run smoke (manual)

**Files:** none — operations-only step.

- [ ] **Step 1: SSH to VPS and verify Claude CLI**

```bash
ssh adnan@135.181.43.68 'claude -p "Reply ECHO" \
  --model claude-opus-4-7 --output-format json \
  --no-session-persistence --tools "" --permission-mode bypassPermissions'
```

Expected: JSON with `"result":"ECHO"`. Confirms OAuth + CLI are live.

- [ ] **Step 2: (Optional) dry-run pipeline on laptop against fake Claude**

```bash
cd ~/Projects/clauding-lab/the-brief
pytest -v -k run_pipeline
```

Expected: pass — no live Claude involved.

- [ ] **Step 3: Phase 3 marker**

```bash
git commit --allow-empty -m "chore(brief): Phase 3 Claude integration complete"
```

---

## Phase 4 — Renderer (~4h)

Python owns HTML. Each section renders a JSX function body from its `SectionData`; `assemble.py` splices the bodies into the existing `the-brief.html` shell by brace-balanced substitution. Cut sections are removed; chart components and `<head>` / `<style>` blocks pass through untouched.

### Task 4.1 — `brief/render/_jsx.py`: JSX-escape + BankerRead helpers

**Files:**
- Create: `brief/render/_jsx.py`
- Test: `tests/render/test_jsx_helpers.py`

- [ ] **Step 1: Failing test**

`tests/render/test_jsx_helpers.py`:

```python
from datetime import date, datetime, timezone

from brief.render._jsx import (
    attr, fmt_num, freshness_pill, bankerread_tag,
)
from brief.schema import BankerReadInsight


def test_attr_escapes_quotes():
    assert attr("title", 'has "quote"') == 'title="has &quot;quote&quot;"'


def test_attr_skips_none():
    assert attr("title", None) == ''


def test_fmt_num_formats_floats():
    assert fmt_num(1234.567, 2) == "1,234.57"
    assert fmt_num(None) == "—"


def test_freshness_pill_stale_adds_pill():
    out = freshness_pill("stale")
    assert "Stale" in out
    assert "pill" in out.lower()


def test_bankerread_tag_uses_joined_sentences():
    br = BankerReadInsight(
        sentences=["a.", "b.", "c.", "d."],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    tag = bankerread_tag(br)
    assert "<BankerRead" in tag
    assert "insight=" in tag
    assert "a. b. c. d." in tag
    assert '"' not in tag.split("insight=")[1][1:].split('"')[0]  # no nested DQ


def test_bankerread_tag_none_returns_empty_string():
    assert bankerread_tag(None) == ""
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/render/test_jsx_helpers.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/render/_jsx.py`**

```python
"""Small JSX helpers shared by every section template."""
from __future__ import annotations

from typing import Optional

from brief.schema import BankerReadInsight, FreshnessKind


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace('"', "&quot;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


def attr(name: str, value: object) -> str:
    """Render a JSX attribute. Returns '' when value is None."""
    if value is None:
        return ""
    return f'{name}="{_esc(str(value))}"'


def fmt_num(n: object, decimals: int = 2) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(n)


_PILL_CLASS = {
    "fresh":       "",
    "warning":     "pill pill-warning",
    "stale":       "pill pill-stale",
    "pending":     "pill pill-pending",
    "unavailable": "pill pill-unavailable",
}


def freshness_pill(kind: FreshnessKind) -> str:
    if kind == "fresh":
        return ""
    label = {
        "warning": "Approaching stale",
        "stale": "Stale",
        "pending": "Awaiting next release",
        "unavailable": "Data missing",
    }[kind]
    cls = _PILL_CLASS[kind]
    return f'<span className="{cls}">{label}</span>'


def bankerread_tag(br: Optional[BankerReadInsight]) -> str:
    if br is None:
        return ""
    joined = " ".join(br.sentences).replace('"', "'").replace("\n", " ")
    return f'<BankerRead insight="{_esc(joined)}" />'
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/render/test_jsx_helpers.py -v`
Expected: PASS (6/6).

- [ ] **Step 5: Commit**

```bash
git add brief/render/_jsx.py tests/render/test_jsx_helpers.py
git commit -m "feat(brief): JSX helpers (attr/fmt_num/pill/bankerread)"
```

### Task 4.2 — `brief/render/assemble.py`: shell splicer

**Files:**
- Create: `brief/render/assemble.py`
- Create: `fixtures/sample_the_brief.html`
- Test: `tests/render/test_assemble.py`

- [ ] **Step 1: Write minimal shell fixture**

`fixtures/sample_the_brief.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><title>TEST</title><style>/* CSS */</style></head>
<body>
<div id="root"></div>
<script type="text/babel">
// ── Components
function MetricCard({label, value}) { return <div>{label}:{value}</div>; }
function BankerRead({insight}) { return <p>{insight}</p>; }

// ── Sections
function SectionBB() {
  return (<section>OLD_BB_BODY</section>);
}

function SectionFX() {
  return (<section>OLD_FX_BODY</section>);
}

function SectionRMG() {
  return (<section>OLD_RMG_BODY</section>);
}

// ── Main App
function App() { return <><SectionBB /><SectionFX /><SectionRMG /></>; }
ReactDOM.render(<App />, document.getElementById('root'));
</script>
</body>
</html>
```

- [ ] **Step 2: Failing test**

`tests/render/test_assemble.py`:

```python
from pathlib import Path

from brief.render.assemble import replace_function_body, remove_function, Shell


SHELL_PATH = Path(__file__).parent.parent.parent / "fixtures" / "sample_the_brief.html"


def test_replace_function_body_swaps_return():
    src = Path(SHELL_PATH).read_text()
    new_body = 'function SectionBB() {\n  return (<section>NEW_BB</section>);\n}'
    out = replace_function_body(src, "SectionBB", new_body)
    assert "NEW_BB" in out
    assert "OLD_BB_BODY" not in out
    assert "OLD_FX_BODY" in out  # untouched


def test_replace_function_body_noop_on_missing():
    src = Path(SHELL_PATH).read_text()
    out = replace_function_body(src, "DoesNotExist", "function X(){}")
    assert out == src


def test_remove_function_drops_definition_and_usage():
    src = Path(SHELL_PATH).read_text()
    out = remove_function(src, "SectionRMG")
    assert "SectionRMG" not in out
    assert "function SectionBB" in out


def test_shell_roundtrip():
    shell = Shell.load(SHELL_PATH)
    assert "OLD_BB_BODY" in shell.text
    shell.replace("SectionBB", "function SectionBB() { return <x/>; }")
    shell.remove_cut_sections(["SectionRMG"])
    assert "OLD_BB_BODY" not in shell.text
    assert "SectionRMG" not in shell.text
```

- [ ] **Step 3: Run — FAIL**

Run: `pytest tests/render/test_assemble.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `brief/render/assemble.py`**

```python
"""Splice per-section JSX into the-brief.html shell.

The shell contains `function SectionXxx() { ... }` definitions inside a
<script type="text/babel"> block. We locate each by name, find the
balanced `{...}` body, and substitute a freshly-rendered full function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


def _brace_end(text: str, start: int) -> int:
    """Return index of the `}` closing the `{` at `start`. Ported from update.py."""
    depth = 0
    in_str: str | None = None
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(text) - 1


def _find_function(text: str, name: str) -> tuple[int, int] | None:
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(\s*\)", text)
    if not m:
        return None
    brace = text.find("{", m.end())
    if brace == -1:
        return None
    end = _brace_end(text, brace)
    return m.start(), end + 1


def replace_function_body(text: str, name: str, new_function: str) -> str:
    span = _find_function(text, name)
    if span is None:
        return text
    start, end = span
    return text[:start] + new_function + text[end:]


def remove_function(text: str, name: str) -> str:
    span = _find_function(text, name)
    if span is not None:
        start, end = span
        text = text[:start] + text[end:]
    # Also drop self-closing usage like <SectionRMG />
    text = re.sub(r"<\s*" + re.escape(name) + r"\s*/\s*>", "", text)
    # And paired <SectionRMG>…</SectionRMG> (defensive; not expected in this shell)
    text = re.sub(
        r"<\s*" + re.escape(name) + r"[^>]*>.*?<\s*/\s*" + re.escape(name) + r"\s*>",
        "", text, flags=re.DOTALL,
    )
    return text


@dataclass
class Shell:
    text: str

    @classmethod
    def load(cls, path: Path | str) -> "Shell":
        return cls(text=Path(path).read_text(encoding="utf-8"))

    def replace(self, name: str, new_function: str) -> None:
        self.text = replace_function_body(self.text, name, new_function)

    def remove_cut_sections(self, names: Iterable[str]) -> None:
        for n in names:
            self.text = remove_function(self.text, n)

    def write(self, path: Path | str) -> None:
        Path(path).write_text(self.text, encoding="utf-8")
```

- [ ] **Step 5: Run — PASS**

Run: `pytest tests/render/test_assemble.py -v`
Expected: PASS (4/4).

- [ ] **Step 6: Commit**

```bash
git add brief/render/assemble.py fixtures/sample_the_brief.html tests/render/test_assemble.py
git commit -m "feat(brief): assemble.py shell splicer + fixture"
```

### Task 4.3 — Template: `section_bb` (full TDD)

**Files:**
- Create: `brief/render/templates/section_bb.py`
- Test: `tests/render/test_section_bb.py`

- [ ] **Step 1: Failing test**

`tests/render/test_section_bb.py`:

```python
from datetime import date, datetime, timezone

from brief.render.templates.section_bb import render
from brief.schema import BankerReadInsight, Delta, Metric, SectionData


def _section(freshness="fresh", with_bankerread=True):
    br = BankerReadInsight(
        sentences=["one.", "two.", "three.", "four."],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    ) if with_bankerread else None
    return SectionData(
        id="bb", title="Policy & Rates",
        metrics=[
            Metric(id="bb_policy_rate", label="Policy Rate", value=10.0, unit="%",
                   as_of=date(2026, 4, 18), source="BB", cadence="event"),
            Metric(id="bb_gross_reserves", label="Reserves", value=34.12, unit="bn USD",
                   as_of=date(2026, 4, 20), source="BB", cadence="weekly",
                   delta=Delta(value=0.3, direction="up", window="wow")),
        ],
        freshness=freshness,
        bankerread=br,
    )


def test_renders_valid_jsx_function():
    out = render(_section())
    assert out.startswith("function SectionBB()")
    assert out.rstrip().endswith("}")
    assert "<section" in out
    assert "Policy Rate" in out
    assert "10.00" in out
    assert "<BankerRead" in out


def test_renders_pill_when_stale():
    out = render(_section(freshness="stale"))
    assert "Stale" in out


def test_renders_without_bankerread_when_missing():
    out = render(_section(with_bankerread=False))
    assert "<BankerRead" not in out
    assert "Policy Rate" in out
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/render/test_section_bb.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `brief/render/templates/section_bb.py`**

```python
"""Render function body for SectionBB."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, fmt_num, freshness_pill
from brief.schema import SectionData


def render(section: SectionData) -> str:
    cards = []
    for m in section.metrics:
        cards.append(
            f'        <MetricCard label="{m.label}" '
            f'value="{fmt_num(m.value)}{m.unit}" />'
        )
    pill = freshness_pill(section.freshness)
    br_tag = bankerread_tag(section.bankerread)
    cards_src = "\n".join(cards)
    return (
        "function SectionBB() {\n"
        "  return (\n"
        f'    <section id="section-bb">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        f"{cards_src}\n"
        f"      {br_tag}\n"
        f"    </section>\n"
        "  );\n"
        "}"
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/render/test_section_bb.py -v`
Expected: PASS (3/3).

- [ ] **Step 5: Commit**

```bash
git add brief/render/templates/section_bb.py tests/render/test_section_bb.py
git commit -m "feat(brief): section_bb template (full TDD)"
```

### Task 4.4 — Generic metric-card renderer for 10 similar sections

Most sections follow the same shape: `<section id=…><h2>Title</h2>{cards}{bankerread}</section>`. Rather than 10 near-identical files, introduce a shared renderer and a per-section factory — each template file simply binds the section id + component name.

**Files:**
- Create: `brief/render/templates/_metric_card_section.py`
- Create: `brief/render/templates/section_macro.py`
- Create: `brief/render/templates/section_fx.py`
- Create: `brief/render/templates/section_remittance.py`
- Create: `brief/render/templates/section_tbond.py`
- Create: `brief/render/templates/section_iranwar.py`
- Create: `brief/render/templates/section_comm.py`
- Create: `brief/render/templates/section_banking.py`
- Create: `brief/render/templates/section_dam.py`
- Create: `brief/render/templates/section_fiscal.py`
- Create: `brief/render/templates/section_nbr.py`
- Test: `tests/render/test_templates_smoke.py`

- [ ] **Step 1: Shared renderer**

`brief/render/templates/_metric_card_section.py`:

```python
"""Generic metric-card section renderer used by most templates."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, fmt_num, freshness_pill
from brief.schema import SectionData


def render_generic(section: SectionData, *, component_name: str,
                   dom_id: str) -> str:
    cards = [
        f'        <MetricCard label="{m.label}" '
        f'value="{fmt_num(m.value)}{m.unit}" />'
        for m in section.metrics
    ]
    cards_src = "\n".join(cards) if cards else '        <div className="empty">No data</div>'
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        f"function {component_name}() {{\n"
        "  return (\n"
        f'    <section id="{dom_id}">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        f"{cards_src}\n"
        f"      {br}\n"
        f"    </section>\n"
        "  );\n"
        "}"
    )
```

- [ ] **Step 2: Per-section binding files**

Each of the 10 binder files — one `render(section)` function that delegates. Pattern:

`brief/render/templates/section_macro.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionMacro", dom_id="section-macro")
```

`brief/render/templates/section_fx.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionFX", dom_id="section-fx")
```

`brief/render/templates/section_remittance.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionRemittance",
                          dom_id="section-remittance")
```

`brief/render/templates/section_tbond.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionTBond", dom_id="section-tbond")
```

`brief/render/templates/section_iranwar.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionIranWar",
                          dom_id="section-iranwar")
```

`brief/render/templates/section_comm.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionComm", dom_id="section-comm")
```

`brief/render/templates/section_banking.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionBanking",
                          dom_id="section-banking")
```

`brief/render/templates/section_dam.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionDAM", dom_id="section-dam")
```

`brief/render/templates/section_fiscal.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionFiscal",
                          dom_id="section-fiscal")
```

`brief/render/templates/section_nbr.py`:

```python
from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionNBR", dom_id="section-nbr")
```

- [ ] **Step 3: Smoke test matrix**

`tests/render/test_templates_smoke.py`:

```python
import importlib
from datetime import date

import pytest

from brief.schema import SectionData


_CASES = [
    ("brief.render.templates.section_macro",      "SectionMacro",      "macro"),
    ("brief.render.templates.section_fx",         "SectionFX",         "fx"),
    ("brief.render.templates.section_remittance", "SectionRemittance", "remit"),
    ("brief.render.templates.section_tbond",      "SectionTBond",      "tbond"),
    ("brief.render.templates.section_iranwar",    "SectionIranWar",    "iranwar"),
    ("brief.render.templates.section_comm",       "SectionComm",       "comm"),
    ("brief.render.templates.section_banking",    "SectionBanking",    "banking"),
    ("brief.render.templates.section_dam",        "SectionDAM",        "dam"),
    ("brief.render.templates.section_fiscal",     "SectionFiscal",     "fiscal"),
    ("brief.render.templates.section_nbr",        "SectionNBR",        "nbr"),
]


@pytest.mark.parametrize("modname,component,sid", _CASES)
def test_template_renders_empty_section(modname, component, sid):
    mod = importlib.import_module(modname)
    s = SectionData(id=sid, title=f"{component} title", freshness="fresh")
    out = mod.render(s)
    assert out.startswith(f"function {component}()")
    assert f'id="section-{sid}"' in out
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/render/test_templates_smoke.py -v`
Expected: PASS (10/10).

- [ ] **Step 5: Commit**

```bash
git add brief/render/templates/ tests/render/test_templates_smoke.py
git commit -m "feat(brief): generic metric-card templates for 10 sections"
```

### Task 4.5 — Template: `section_dse` (custom — breadth row)

**Files:**
- Create: `brief/render/templates/section_dse.py`
- Test: `tests/render/test_section_dse.py`

- [ ] **Step 1: Failing test**

```python
from datetime import date

from brief.render.templates.section_dse import render
from brief.schema import Metric, SectionData


def _section():
    base_kwargs = dict(unit="x", as_of=date(2026, 4, 20), source="DSE", cadence="daily")
    return SectionData(
        id="dse", title="DSE Markets",
        metrics=[
            Metric(id="dse_dsex_close", label="DSEX", value=5232.49, **base_kwargs),
            Metric(id="dse_advancing", label="Advancing", value=120, **base_kwargs),
            Metric(id="dse_declining", label="Declining", value=207, **base_kwargs),
        ],
        freshness="fresh",
    )


def test_dse_render_shows_breadth():
    out = render(_section())
    assert out.startswith("function SectionDSE()")
    assert "5,232.49" in out
    assert "Advancing" in out
    assert "Declining" in out
    assert 'id="section-dse"' in out
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/render/test_section_dse.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementation**

```python
"""SectionDSE — DSEX close + breadth strip."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, fmt_num, freshness_pill
from brief.schema import SectionData


def render(section: SectionData) -> str:
    def find(mid: str):
        return next((m for m in section.metrics if m.id == mid), None)

    dsex = find("dse_dsex_close")
    change = find("dse_dsex_change_pct")
    advancing = find("dse_advancing")
    declining = find("dse_declining")

    dsex_line = (
        f'<MetricCard label="DSEX" '
        f'value="{fmt_num(dsex.value if dsex else None)}" '
        f'change="{fmt_num(change.value if change else None, 2)}%" />'
    )
    breadth_line = (
        f'<div className="breadth">Advancing {int(advancing.value) if advancing and advancing.value else "—"} · '
        f'Declining {int(declining.value) if declining and declining.value else "—"}</div>'
    )
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        "function SectionDSE() {\n"
        "  return (\n"
        '    <section id="section-dse">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        f"      {dsex_line}\n"
        f"      {breadth_line}\n"
        f"      {br}\n"
        "    </section>\n"
        "  );\n"
        "}"
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/render/test_section_dse.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/render/templates/section_dse.py tests/render/test_section_dse.py
git commit -m "feat(brief): section_dse template (close + breadth)"
```

### Task 4.6 — Template: `section_headlines`

**Files:**
- Create: `brief/render/templates/section_headlines.py`
- Test: `tests/render/test_section_headlines.py`

- [ ] **Step 1: Failing test**

```python
from datetime import datetime, timezone

from brief.render.templates.section_headlines import render
from brief.schema import NewsItem, SectionData


def _section():
    return SectionData(
        id="headlines", title="Headlines", freshness="fresh",
        news=[
            NewsItem(title="BB holds rate", url="https://x/1",
                     source="DS", published=datetime(2026, 4, 21, tzinfo=timezone.utc)),
            NewsItem(title='Budget "big" day', url="https://x/2",
                     source="TBS", published=datetime(2026, 4, 21, tzinfo=timezone.utc)),
        ],
    )


def test_headlines_render_escapes_quotes():
    out = render(_section())
    assert out.startswith("function SectionHeadlines()")
    assert "BB holds rate" in out
    assert "&quot;big&quot;" in out
    assert "https://x/1" in out
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/render/test_section_headlines.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementation**

```python
"""SectionHeadlines — renders a JS array literal of news items."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, freshness_pill
from brief.schema import SectionData


def _esc_js(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace('"', '&quot;')
         .replace("\n", " ")
    )


def render(section: SectionData) -> str:
    items = ",\n".join(
        f'    {{ title: "{_esc_js(n.title)}", url: "{_esc_js(n.url)}", '
        f'source: "{_esc_js(n.source)}", time: "{n.published.date().isoformat()}" }}'
        for n in section.news
    )
    array_literal = "[\n" + items + "\n  ]" if section.news else "[]"
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        "function SectionHeadlines() {\n"
        f"  const headlines = {array_literal};\n"
        "  return (\n"
        '    <section id="section-headlines">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        "      {headlines.map(h => (\n"
        '        <a key={h.url} href={h.url}>[{h.source}] {h.title} <time>{h.time}</time></a>\n'
        "      ))}\n"
        f"      {br}\n"
        "    </section>\n"
        "  );\n"
        "}"
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/render/test_section_headlines.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/render/templates/section_headlines.py tests/render/test_section_headlines.py
git commit -m "feat(brief): section_headlines template"
```

### Task 4.7 — Template: `section_exec`

**Files:**
- Create: `brief/render/templates/section_exec.py`
- Test: `tests/render/test_section_exec.py`

- [ ] **Step 1: Failing test**

```python
from brief.render.templates.section_exec import render
from brief.schema import ExecSignal, SectionData


def _section():
    return SectionData(
        id="exec", title="Executive Signals", freshness="fresh",
        exec_signals=[
            ExecSignal(direction="bull", text="Reserves up 0.3bn WoW",
                       section_anchor="bb"),
            ExecSignal(direction="warn", text="Oil +5% on Iran risk",
                       section_anchor="iranwar"),
        ],
    )


def test_exec_render_shows_signals():
    out = render(_section())
    assert out.startswith("function SectionExec()")
    assert "Reserves up" in out
    assert "Oil +5%" in out
    assert 'direction: "bull"' in out
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/render/test_section_exec.py -v`
Expected: FAIL.

- [ ] **Step 3: Implementation**

```python
"""SectionExec — renders a JS array literal of exec signals."""
from __future__ import annotations

from brief.render._jsx import bankerread_tag, freshness_pill
from brief.schema import SectionData


def _esc_js(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '&quot;').replace("\n", " ")


def render(section: SectionData) -> str:
    signals = section.exec_signals or []
    items = ",\n".join(
        f'    {{ direction: "{_esc_js(s.direction)}", '
        f'text: "{_esc_js(s.text)}", '
        f'section: "{_esc_js(s.section_anchor)}" }}'
        for s in signals
    )
    array_literal = "[\n" + items + "\n  ]" if signals else "[]"
    pill = freshness_pill(section.freshness)
    br = bankerread_tag(section.bankerread)
    return (
        "function SectionExec() {\n"
        f"  const signals = {array_literal};\n"
        "  return (\n"
        '    <section id="section-exec">\n'
        f"      <h2>{section.title}{pill}</h2>\n"
        "      {signals.map((s, i) => (\n"
        '        <div key={i} className={"sig sig-" + s.direction}>{s.text}</div>\n'
        "      ))}\n"
        f"      {br}\n"
        "    </section>\n"
        "  );\n"
        "}"
    )
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/render/test_section_exec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/render/templates/section_exec.py tests/render/test_section_exec.py
git commit -m "feat(brief): section_exec template"
```

### Task 4.8 — Render orchestrator: `render.assemble_brief`

**Files:**
- Modify: `brief/render/assemble.py`
- Test: `tests/render/test_assemble.py` (append)

- [ ] **Step 1: Append failing test**

```python
import importlib
from datetime import date, datetime, timezone

from brief.render.assemble import assemble_brief
from brief.schema import BankerReadInsight, Metric, SectionData


def _section(sid: str, title: str, *, with_br=True) -> SectionData:
    br = BankerReadInsight(
        sentences=[f"{sid} one.", "two.", "three.", "four."],
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    ) if with_br else None
    return SectionData(
        id=sid, title=title, freshness="fresh",
        metrics=[
            Metric(id=f"{sid}_a", label="A", value=1.0, unit="x",
                   as_of=date(2026, 4, 21), source="t", cadence="daily"),
        ],
        bankerread=br,
    )


def test_assemble_brief_replaces_bb_and_fx_removes_rmg():
    sections = [_section("bb", "Policy"), _section("fx", "FX")]
    out = assemble_brief(SHELL_PATH, sections)
    assert "OLD_BB_BODY" not in out
    assert "OLD_FX_BODY" not in out
    assert "OLD_RMG_BODY" not in out
    assert "Policy" in out
    assert "FX" in out
    assert "SectionRMG" not in out
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/render/test_assemble.py -v`
Expected: FAIL.

- [ ] **Step 3: Extend `brief/render/assemble.py`**

Append:

```python
import importlib as _importlib
from typing import Iterable as _Iterable

from brief.schema import SectionData as _SectionData


_SECTION_TO_TEMPLATE: dict[str, tuple[str, str]] = {
    # section id -> (template module, React component name to replace)
    "bb":         ("brief.render.templates.section_bb",         "SectionBB"),
    "macro":      ("brief.render.templates.section_macro",      "SectionMacro"),
    "fx":         ("brief.render.templates.section_fx",         "SectionFX"),
    "remit":      ("brief.render.templates.section_remittance", "SectionRemittance"),
    "dse":        ("brief.render.templates.section_dse",        "SectionDSE"),
    "tbond":      ("brief.render.templates.section_tbond",      "SectionTBond"),
    "iranwar":    ("brief.render.templates.section_iranwar",    "SectionIranWar"),
    "headlines":  ("brief.render.templates.section_headlines",  "SectionHeadlines"),
    "exec":       ("brief.render.templates.section_exec",       "SectionExec"),
    "comm":       ("brief.render.templates.section_comm",       "SectionComm"),
    "banking":    ("brief.render.templates.section_banking",    "SectionBanking"),
    "dam":        ("brief.render.templates.section_dam",        "SectionDAM"),
    "fiscal":     ("brief.render.templates.section_fiscal",     "SectionFiscal"),
    "nbr":        ("brief.render.templates.section_nbr",        "SectionNBR"),
}

CUT_SECTIONS = ("SectionRMG", "SectionPower", "SectionPeers")


def assemble_brief(
    shell_path: Path | str,
    sections: _Iterable[_SectionData],
) -> str:
    shell = Shell.load(shell_path)
    for section in sections:
        mapping = _SECTION_TO_TEMPLATE.get(section.id)
        if mapping is None:
            continue
        mod_name, component_name = mapping
        mod = _importlib.import_module(mod_name)
        new_body = mod.render(section)
        shell.replace(component_name, new_body)
    shell.remove_cut_sections(CUT_SECTIONS)
    return shell.text
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/render/test_assemble.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/render/assemble.py tests/render/test_assemble.py
git commit -m "feat(brief): assemble_brief orchestrator (14 sections + cuts)"
```

### Task 4.9 — Pipeline: add `render()` + `run()` end-to-end

**Files:**
- Modify: `brief/pipeline.py`
- Test: `tests/test_pipeline_integration.py` (append)

- [ ] **Step 1: Append failing test**

```python
from pathlib import Path

FIXTURE_SHELL = Path(__file__).parent.parent / "fixtures" / "sample_the_brief.html"


def test_run_returns_html(fixture_snapshot, today):
    from brief.pipeline import PipelineConfig, run
    cfg = PipelineConfig(
        today=today, enable_history=False, enable_headlines=False,
    )
    with patch("brief.pipeline.run_max") as mx:
        mx.side_effect = [_fake_curation([]), _fake_signals(), _fake_insights()]
        result = run(cfg, shell_path=FIXTURE_SHELL, snapshot_override=fixture_snapshot)
    assert "OLD_BB_BODY" not in result.html
    assert "SectionRMG" not in result.html
    assert result.html.startswith("<!DOCTYPE html>")
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/test_pipeline_integration.py -v -k test_run_returns_html`
Expected: FAIL.

- [ ] **Step 3: Extend `brief/pipeline.py`**

Append:

```python
from pathlib import Path as _Path

from brief.render.assemble import assemble_brief


@_dc
class RunResult:
    sections: list
    html: str
    claude_outputs: dict
    call_reports: list[dict]


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
```

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_pipeline_integration.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/pipeline.py tests/test_pipeline_integration.py
git commit -m "feat(brief): pipeline.run() end-to-end (gather+claude+render)"
```

### Task 4.10 — `build.sh` fidelity check against real shell

**Files:** (no file changes; validation-only)

- [ ] **Step 1: Generate a shadow HTML from real shell using mocked Claude**

Run:

```bash
cd ~/Projects/clauding-lab/the-brief
ECONDELTA_DATA=$PWD/fixtures/econdelta_latest.json \
python - <<'PY'
from pathlib import Path
from unittest.mock import patch
from datetime import date

from brief.pipeline import PipelineConfig, run
from brief.claude.max_client import MaxCallResult

def _r(payload):
    return MaxCallResult(raw_text="{}", parsed=payload, usage={}, total_cost_usd=0)

stubs = [
    _r({"selected": [], "rationale_bullet": "x"}),
    _r({"signals": [{"direction": "bull", "text": "reserves up", "section_anchor": "bb"}],
        "traffic_status": "neu"}),
    _r({"insights": {sid: ["one.", "two.", "three.", "four."] for sid in
                     ["bb","macro","fx","remit","dse","tbond","iranwar",
                      "headlines","exec","comm","banking","dam","fiscal","nbr"]}}),
]
with patch("brief.pipeline.run_max", side_effect=stubs):
    result = run(PipelineConfig(today=date(2026, 4, 21),
                                enable_history=False, enable_headlines=False),
                 shell_path=Path("the-brief.html"))
Path("index.shadow.html").write_text(result.html, encoding="utf-8")
print(f"shadow size = {len(result.html):,} bytes")
PY
```

Expected: `index.shadow.html` written; printed size within ±40% of live `index.html`.

- [ ] **Step 2: Run `build.sh` on the shadow HTML**

```bash
cp index.shadow.html the-brief.shadow.html
python3 - <<'PY'
import re
from pathlib import Path
src = Path("the-brief.shadow.html").read_text()
m = re.search(r'<script type="text/babel">(.*?)</script>', src, re.DOTALL)
assert m, "babel script block missing — renderer broke the shell"
print("babel block found OK — length", len(m.group(1)))
PY
```

Expected: asserts pass. (Full `build.sh` run via esbuild is optional in Phase 4; a failure there is a downstream template fix, not a shell-splice bug.)

- [ ] **Step 3: Clean up shadow files**

```bash
rm -f index.shadow.html the-brief.shadow.html
```

- [ ] **Step 4: Commit a marker**

```bash
git commit --allow-empty -m "chore(brief): Phase 4 renderer complete"
```

### Task 4.11 — Phase 4 exit gate

- [ ] **Step 1: Full test run with coverage**

Run: `pytest`
Expected: all PASS, coverage ≥80% across `brief/`.

- [ ] **Step 2: Lint sanity (manual)**

Review diffs against the spec's §3 repo layout. Each listed file exists or is explicitly deferred with a note in this plan.

- [ ] **Step 3: Push branch for review**

```bash
git push origin feat/redesign-data-driven
gh pr view 1 --web || true   # sanity link to the spec PR
```

---

## Deferred / out of scope for Part 1

These are spec-adjacent items intentionally handled elsewhere:

- **YieldCurveChart data source** — charts read Supabase `tb_*` tables at page load; the renderer does not touch those function bodies. Decision pending: scrape BB `monetaryactivity/treasury` from this pipeline vs. extend EconDelta. Not blocking Phase 1–4.
- **DSEXChart / TBillChart / OilChart / LNGChart** — Supabase-backed at runtime. The renderer preserves their function bodies untouched (they are not in `_SECTION_TO_TEMPLATE`). DSEX upsert happens in `builders/dse.py` (Task 2.9); LNG upsert remains in existing `update.py` for now and migrates in the ops Part 2 plan.
- **Supabase RLS policies** — `metric_history` enables RLS in migration but defines no policies, meaning service key only. Any future `anon`/`authenticated` access gets its own migration.
- **Headline scraper hardening** — `brief/headlines.py` is a verbatim port; extending sources (Reuters, FT, BBC, AJ, BSS, NYT) lands in Phase 2.x of the ops plan.
- **`build.sh` integration** — Phase 4 checks the shell remains parseable. A full `build.sh` run (esbuild JSX compile) runs as part of Phase 5 VPS deploy and the shadow soak diff in Phase 6.
- **`update.py` removal** — kept side-by-side through Phase 6 shadow soak. The ops plan (Part 2) swaps the entrypoint and deletes `update.py` after 7 clean days.
- **`brief/report.py` (`run_report.json` + Discord)** — lives in Phase 5/6 ops plan (spec §6 last block). Phase 4 exposes `RunResult.call_reports` which Phase 5 serialises.
- **Builder naming divergence from spec §3** — spec lists `builders/remittance.py`; this plan uses `builders/remit.py` to keep file name aligned with the section id used across validators, templates, and registries. The JSX component name `SectionRemittance` is unchanged. This is a deliberate consistency choice.

## Self-review summary

- **Spec coverage** — §3 layout (brief/schema, cadence, econdelta, history, pipeline, builders, claude, render), §4 data contracts, §5 three Claude calls with validators + fallbacks, §6 cadence + `metric_history` + run-report shape, §7 section inventory (13 spine + 5 keep built; 3 cut dropped), §8 Phases 1–4 migration sequence — all mapped to tasks in this plan. Phases 5–6 and parts of §6 (`run_report.json` Discord notify) are by design in the Part 2 ops plan.
- **Placeholder scan** — grep for TBD / TODO / "Similar to" / "fill in" returns zero hits. Every code step contains the code the engineer writes.
- **Type consistency** — `Metric.value: float | int | str | None` everywhere; `SectionData.id` is the short lowercase id used by registries, validators, prompt allow-lists, and template router. `BuilderContext.history` is `Optional[MetricHistoryClient]` consistently. `run_max` is imported into `brief/pipeline` at module scope so tests can `patch("brief.pipeline.run_max")`.
- **Known tight spots** — `run_max` timeout for `bankerread` is 1800s (matches spec §5); validators never raise; `assemble_brief` is robust to missing templates via `_SECTION_TO_TEMPLATE.get()`; cut-section removal is idempotent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-brief-redesign-part1-foundations-through-render.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?






