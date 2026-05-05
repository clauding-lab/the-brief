# Fresh Brief Every Morning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-05-fresh-brief-design.md`

**Goal:** Make the V6 daily brief feel fresh every morning by encoding five editorial-discipline directives — deterministic post-LLM diff stamping, headline re-run filtering, held-over honesty, data-driven daily lens (Mon–Thu), and Friday weekly wrap — into the publish pipeline.

**Architecture:** Add four pure-function builders (`stamp_changed`, `filter_headlines`, `mark_held_overs`, `score_lens`) around the two LLM calls. Editor receives a chosen lens; deterministic primitives stamp diff/held-over flags post-LLM. Friday branches to a separate weekly-wrap prompt. SPA gains a third visual state for held-overs and a lens pill on the masthead.

**Tech Stack:** Python 3.12 (Pydantic v2, pytest), Supabase Postgres (raw SQL migrations applied via Supabase MCP), Next.js 16 App Router (TypeScript, React Server Components), CSS modules in `app/globals.css`.

**Test runner:** `.venv/bin/python -m pytest` for Python; `pnpm test` for SPA snapshots (already wired in repo).

---

## File structure

### NEW files

| File | Responsibility |
|---|---|
| `brief/builders/__init__.py` | Builders package marker (empty) |
| `brief/builders/diff.py` | `stamp_changed()` and `mark_held_overs()` pure functions |
| `brief/builders/dedup.py` | `filter_headlines()` pure function |
| `brief/builders/lens.py` | `score_lens()` pure function |
| `brief/builders/weekly.py` | `_build_weekly_diffs()` for Friday wrap |
| `brief/claude/prompts/editor_v6_friday.txt` | Friday-only editor prompt for weekly wrap |
| `migrations/006_v6_freshness.sql` | Adds held_from / next_print / lens / frame columns |
| `tests/builders/__init__.py` | Test package marker |
| `tests/builders/test_diff.py` | Unit tests for `stamp_changed` + `mark_held_overs` |
| `tests/builders/test_dedup.py` | Unit tests for `filter_headlines` |
| `tests/builders/test_lens.py` | Unit tests for `score_lens` |
| `tests/builders/test_weekly.py` | Unit tests for `_build_weekly_diffs` |
| `tests/test_pipeline_v6_friday.py` | Integration test for Friday branch |
| `tests/fixtures/v6_previous_brief.json` | Frozen previous brief for diff/lens tests |
| `tests/fixtures/v6_metric_definitions.json` | Subset of catalog with cadences for held-over tests |
| `app/components/MastheadLensPill.tsx` | Small pill rendering "Mon · banking lens" |

### MODIFIED files

| File | Lines | Change |
|---|---|---|
| `brief/v6_schema.py` | 33–73 | Add `held_from`, `next_print` to MetricV6/NewsItemV6/CoverMetricV6; add `lens`, `frame` to BriefV6 |
| `brief/v6_publisher.py` | 138–149, 173–177 | Pass new columns to Supabase INSERTs |
| `brief/pipeline_v6.py` | 80–97, 127–209 | Wire score_lens, filter_headlines, stamp_changed, mark_held_overs; Friday branch |
| `brief/claude/prompts/editor_v6.txt` | 80–86, 113, 16–23, 47–52, 104–110 | Five surgical changes (drop NPL rule, 4→12 headlines, frame instruction, schema doc, stale-data tightening) |
| `types/brief.ts` | 30–55 | Add `held_from`, `next_print`, `lens`, `frame` fields |
| `app/components/Section.tsx` | 36, 92–116, 134–141 | Three-state rendering (changed/held_over/default) |
| `app/components/Cover.tsx` | 52–67 | Held-over rendering for cover-line |
| `app/components/StatStack.tsx` | 13–44 | Held-over indicator + footer |
| `app/components/Masthead.tsx` | (existing or new) | Mount MastheadLensPill |
| `app/globals.css` | 661–705 | Add `.is-held-over` class; update `body.tb-diff` rules |

---

## Phase 0: Setup

### Task 0.1: Create implementation worktree

**Files:** none (git scaffolding)

- [ ] **Step 1: Create a clean worktree off main**

```bash
cd ~/Projects/clauding-lab/the-brief
git fetch origin && git checkout main && git pull --ff-only
git worktree add .worktrees/fresh-brief feat/fresh-brief
cd .worktrees/fresh-brief
```

- [ ] **Step 2: Verify clean state**

```bash
git status
git log -1 --oneline
.venv/bin/python -m pytest --no-cov -q tests/ 2>&1 | tail -5
```

Expected: clean working tree, on `feat/fresh-brief`, all current tests passing.

If `.venv` doesn't exist in the worktree (it usually doesn't because `.gitignore` ignores it), create one:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install "setuptools<80"
```

- [ ] **Step 3: Commit nothing yet**

The branch starts identical to main. First commit happens in Task 1.1.

---

## Phase 1: Schema + Pydantic + TS types (no behavior change)

This phase ships migrations and type additions only. All new columns are nullable. Existing reads/writes continue to work because new fields default to NULL/None.

### Task 1.1: Supabase migration

**Files:**
- Create: `migrations/006_v6_freshness.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migrations/006_v6_freshness.sql
-- Adds freshness annotation columns for V6 fresh-brief plan.
-- All new columns nullable; populated post-LLM by builders.

ALTER TABLE metrics ADD COLUMN held_from DATE;
ALTER TABLE metrics ADD COLUMN next_print TEXT;

ALTER TABLE news ADD COLUMN held_from DATE;

ALTER TABLE briefs ADD COLUMN lens TEXT;
ALTER TABLE briefs ADD COLUMN frame TEXT;

COMMENT ON COLUMN metrics.held_from IS 'Date this exact metric value first appeared (held-over from this issue). NULL = fresh today.';
COMMENT ON COLUMN metrics.next_print IS 'Free-text label for next expected publication, e.g. "Q1 2026 in late July".';
COMMENT ON COLUMN news.held_from IS 'Date this exact headline first appeared in a brief. NULL = fresh today. Rare — most repeats are filtered upstream.';
COMMENT ON COLUMN briefs.lens IS 'Today''s editorial lens (banking|fx|dse|tbond|macro|iran|weekly_wrap). Drives hero section + cover metric.';
COMMENT ON COLUMN briefs.frame IS 'Today''s editorial frame (sovereign-debt|FX-runway|credit-cycle|rates-curve|external-shock|weekly-wrap). Drives todays_call prose structure.';
```

- [ ] **Step 2: Apply migration via Supabase MCP**

The agent should call `mcp__plugin_supabase_supabase__apply_migration` with `project_id="ssbliukchgibjcjohibi"`, `name="006_v6_freshness"`, and `query` set to the SQL above (or paste the SQL directly).

- [ ] **Step 3: Verify columns exist**

Call `mcp__plugin_supabase_supabase__execute_sql` with:

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name IN ('metrics','news','briefs')
  AND column_name IN ('held_from','next_print','lens','frame')
ORDER BY table_name, column_name;
```

Expected: 5 rows — `briefs.frame`, `briefs.lens`, `metrics.held_from`, `metrics.next_print`, `news.held_from`. All `is_nullable=YES`.

- [ ] **Step 4: Commit**

```bash
git add migrations/006_v6_freshness.sql
git commit -m "feat(schema): add freshness columns for V6 (held_from, next_print, lens, frame)"
```

---

### Task 1.2: Pydantic schema additions

**Files:**
- Modify: `brief/v6_schema.py`

- [ ] **Step 1: Write the failing test first**

Create `tests/test_v6_schema_freshness.py`:

```python
"""Verify new freshness fields parse cleanly with sensible defaults."""
from datetime import date

from brief.v6_schema import BriefV6, CoverMetricV6, MetricV6, NewsItemV6


def test_metric_accepts_held_from():
    m = MetricV6(label="NPL Ratio", value="35.73%", held_from="2026-04-18", next_print="Q1 2026")
    assert m.held_from == date(2026, 4, 18)
    assert m.next_print == "Q1 2026"


def test_metric_held_from_optional():
    m = MetricV6(label="Brent", value="$113.95")
    assert m.held_from is None
    assert m.next_print is None


def test_news_accepts_held_from():
    n = NewsItemV6(headline="X happened", held_from="2026-05-01")
    assert n.held_from == date(2026, 5, 1)


def test_brief_accepts_lens_and_frame():
    b = BriefV6(issue_no=1, volume=1, brief_date="2026-05-05", lens="banking", frame="credit-cycle")
    assert b.lens == "banking"
    assert b.frame == "credit-cycle"


def test_cover_metric_accepts_held_from():
    c = CoverMetricV6(label="NPL", value="35.73%", held_from="2026-04-18", next_print="Q1 2026")
    assert c.held_from == date(2026, 4, 18)
    assert c.next_print == "Q1 2026"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_v6_schema_freshness.py -v
```

Expected: 5 tests fail with `ValidationError` ("extra fields forbidden" on BriefV6) or `AttributeError`.

- [ ] **Step 3: Add fields to v6_schema.py**

In `brief/v6_schema.py`, add three changes (use the exact existing surrounding code as anchors for Edit operations):

(a) `MetricV6` (around line 52–62) — append two fields:

```python
class MetricV6(_Lenient):
    label: str
    value: str
    sub: Optional[str] = None
    tone: Optional[Tone] = None
    is_snapshot: Optional[bool] = False
    spark: Optional[list[float]] = None
    delta: Optional[str] = None
    delta_pct: Optional[str] = None
    changed: Optional[bool] = False
    weight: Optional[int] = Field(default=1, ge=1, le=2)
    held_from: Optional[date_t] = None
    next_print: Optional[str] = None
```

(b) `NewsItemV6` (around line 65–72) — append one field:

```python
class NewsItemV6(_Lenient):
    headline: str
    detail: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    tone: Optional[Tone] = None
    changed: Optional[bool] = False
    held_from: Optional[date_t] = None
```

(c) `CoverMetricV6` (around line 33–39) — append two fields:

```python
class CoverMetricV6(_Lenient):
    label: str
    value: str
    sub: Optional[str] = None
    tone: Optional[Tone] = None
    section_slug: Optional[str] = None
    as_of: Optional[str] = None
    held_from: Optional[date_t] = None
    next_print: Optional[str] = None
```

(d) `BriefV6` (around line 42–49) — append two fields:

```python
class BriefV6(_Strict):
    issue_no: int = Field(ge=1)
    volume: int = Field(ge=1)
    brief_date: date_t
    read_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    cover_metric: Optional[CoverMetricV6] = None
    todays_call: Optional[str] = None
    status: Optional[Literal["draft", "published", "archived"]] = "published"
    lens: Optional[str] = None
    frame: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_v6_schema_freshness.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full suite to verify no regression**

```bash
.venv/bin/python -m pytest --no-cov -q
```

Expected: all green (no other tests touch these models with `extra="forbid"` constraints that would break).

- [ ] **Step 6: Commit**

```bash
git add brief/v6_schema.py tests/test_v6_schema_freshness.py
git commit -m "feat(schema): add held_from/next_print/lens/frame to V6 Pydantic models"
```

---

### Task 1.3: TypeScript type additions

**Files:**
- Modify: `types/brief.ts`

- [ ] **Step 1: Read current types file**

Open `types/brief.ts` to find the existing `Metric`, `NewsItem`, `CoverMetric`, `Brief` interfaces.

- [ ] **Step 2: Add fields**

Add the following optional fields to the matching TypeScript interfaces:

```typescript
// Metric
held_from?: string;     // ISO date or null
next_print?: string;    // free-text label

// NewsItem
held_from?: string;

// CoverMetric
held_from?: string;
next_print?: string;

// Brief
lens?: string;
frame?: string;
```

The exact surrounding lines depend on what's already in the file. Use `Read` then `Edit` to insert each field next to existing similar `?:` fields.

- [ ] **Step 3: Run TS typecheck**

```bash
pnpm tsc --noEmit
```

Expected: no errors. (Adding optional fields is additive.)

- [ ] **Step 4: Run SPA test suite**

```bash
pnpm test --run
```

Expected: existing tests pass; no rendering of new fields yet so nothing should break.

- [ ] **Step 5: Commit**

```bash
git add types/brief.ts
git commit -m "feat(types): add held_from/next_print/lens/frame TS types"
```

---

### Task 1.4: Open PR for Phase 1

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/fresh-brief
```

- [ ] **Step 2: Open PR (Phase 1 only, but mark as Stack 1/5)**

```bash
gh pr create --title "feat: V1 fresh-brief — Phase 1 schema + types" --body "$(cat <<'EOF'
## Summary

Stack 1/5 of the "Fresh Brief" V1 plan. Schema-only changes. No runtime behavior change.

- Adds `held_from`, `next_print`, `lens`, `frame` columns to Supabase (`metrics`, `news`, `briefs`)
- Mirrors fields in `brief/v6_schema.py` Pydantic models
- Mirrors fields in `types/brief.ts` for the SPA

Spec: `docs/superpowers/specs/2026-05-05-fresh-brief-design.md`
Plan: `docs/superpowers/plans/2026-05-05-fresh-brief.md`

## Test plan

- [x] `pytest tests/test_v6_schema_freshness.py` — 5 new tests pass
- [x] `pytest` full suite — no regression
- [x] `pnpm tsc --noEmit` — no errors
- [x] Migration applied to Supabase prod via MCP
- [ ] Mon–Fri timer fires continue to work (Phase 1 is additive, no wiring change yet)
EOF
)"
```

- [ ] **Step 3: Wait for green CI, then ask user for approval to merge**

DO NOT merge autonomously — PR merges require user per-action approval per the user's shared-state rule. Stop here and ask.

---

## Phase 2: Diff primitives (pure functions, not yet wired)

### Task 2.1: `stamp_changed` — diff news + metrics against previous brief

**Files:**
- Create: `brief/builders/__init__.py` (empty)
- Create: `brief/builders/diff.py`
- Create: `tests/builders/__init__.py` (empty)
- Create: `tests/builders/test_diff.py`
- Create: `tests/fixtures/v6_previous_brief.json`

- [ ] **Step 1: Write the previous-brief fixture**

`tests/fixtures/v6_previous_brief.json`:

```json
{
  "brief": {
    "issue_no": 90,
    "volume": 1,
    "brief_date": "2026-05-04",
    "status": "published"
  },
  "sections": [
    {
      "slug": "banking",
      "ord": 4,
      "title": "Banking",
      "group_key": "banking",
      "metrics": [
        {"label": "NPL Ratio", "value": "35.73%", "tone": "bear"},
        {"label": "CAR", "value": "1.56%", "tone": "bear"}
      ],
      "news": [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?", "source_url": "https://example.com/refinance"},
        {"headline": "DSE brokers urge BSEC to lift floor price on Beximco, Islami Bank", "source_url": "https://example.com/floor"}
      ]
    },
    {
      "slug": "iran",
      "ord": 10,
      "title": "External · Iran",
      "group_key": "policy",
      "metrics": [
        {"label": "Brent Spot", "value": "$107.56"}
      ],
      "news": []
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

`tests/builders/test_diff.py`:

```python
"""Unit tests for stamp_changed and mark_held_overs."""
import json
from pathlib import Path

import pytest

from brief.builders.diff import stamp_changed
from brief.v6_schema import BriefPayloadV6, NewsItemV6, MetricV6, SectionV6, BriefV6


FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def previous_brief() -> dict:
    return json.loads((FIXTURES / "v6_previous_brief.json").read_text())


def _make_brief(metrics_by_section: dict[str, list[dict]], news_by_section: dict[str, list[dict]]) -> BriefPayloadV6:
    sections = []
    for slug, metrics in metrics_by_section.items():
        sections.append(SectionV6(
            slug=slug,
            ord=1,
            title=slug.title(),
            group_key="banking" if slug in ("banking", "bb") else "markets",
            metrics=[MetricV6(**m) for m in metrics],
            news=[NewsItemV6(**n) for n in news_by_section.get(slug, [])],
        ))
    return BriefPayloadV6(
        brief=BriefV6(issue_no=91, volume=1, brief_date="2026-05-05"),
        sections=sections,
    )


def test_metric_value_unchanged_marked_false(previous_brief):
    """NPL 35.73% in both briefs → changed=False."""
    current = _make_brief({"banking": [{"label": "NPL Ratio", "value": "35.73%"}]}, {})
    stamp_changed(current, previous_brief)
    assert current.sections[0].metrics[0].changed is False


def test_metric_value_moved_marked_true(previous_brief):
    """Brent moved $107.56 → $113.95 → changed=True."""
    current = _make_brief({"iran": [{"label": "Brent Spot", "value": "$113.95"}]}, {})
    stamp_changed(current, previous_brief)
    assert current.sections[0].metrics[0].changed is True


def test_metric_new_marked_true(previous_brief):
    """A metric that didn't exist before → changed=True."""
    current = _make_brief({"banking": [{"label": "Reserve Money", "value": "Tk 4.2tn"}]}, {})
    stamp_changed(current, previous_brief)
    assert current.sections[0].metrics[0].changed is True


def test_news_exact_match_marked_false(previous_brief):
    """Same headline + same URL → changed=False (this is the bug we're fixing)."""
    current = _make_brief({}, {"banking": [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance"}
    ]})
    stamp_changed(current, previous_brief)
    assert current.sections[0].news[0].changed is False


def test_news_new_url_marked_true(previous_brief):
    """Same headline text, different URL → changed=True (likely a fresh article)."""
    current = _make_brief({}, {"banking": [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?",
         "source_url": "https://example.com/refinance-update"}
    ]})
    stamp_changed(current, previous_brief)
    assert current.sections[0].news[0].changed is True


def test_news_normalized_match(previous_brief):
    """Same headline with different punctuation/case → changed=False."""
    current = _make_brief({}, {"banking": [
        {"headline": "WILL CENBANK'S TK40,000CR REFINANCE SCHEME FUEL INFLATION??",
         "source_url": "https://example.com/refinance"}
    ]})
    stamp_changed(current, previous_brief)
    assert current.sections[0].news[0].changed is False


def test_no_previous_brief_marks_everything_true():
    """Cold start: previous_brief=None → all changed=True."""
    current = _make_brief(
        {"banking": [{"label": "NPL", "value": "35%"}]},
        {"banking": [{"headline": "Anything", "source_url": "x"}]}
    )
    stamp_changed(current, None)
    assert current.sections[0].metrics[0].changed is True
    assert current.sections[0].news[0].changed is True
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/builders/test_diff.py -v
```

Expected: 7 tests fail with `ImportError: cannot import name 'stamp_changed'`.

- [ ] **Step 4: Write the implementation**

`brief/builders/__init__.py`: empty file.

`brief/builders/diff.py`:

```python
"""Deterministic post-LLM diff stamping for V6 briefs.

Walks the editor's output against the previous published brief and stamps
`changed=true/false` on every news item and metric. Replaces the missing
diff signal that V5 used to compute and that V6 dropped.
"""
from __future__ import annotations

import re
from typing import Any

from brief.v6_schema import BriefPayloadV6


_PUNCT_WHITESPACE = re.compile(r"[^\w]+")


def _normalize_headline(text: str) -> str:
    """Lowercase + strip non-word characters. Whitespace and punctuation collapse."""
    return _PUNCT_WHITESPACE.sub("", text.lower())


def _index_previous_news(previous_brief: dict[str, Any] | None) -> set[tuple[str, str]]:
    """Build a set of (headline_normalized, source_url) keys from the previous brief."""
    if not previous_brief:
        return set()
    keys: set[tuple[str, str]] = set()
    for section in previous_brief.get("sections", []):
        for n in section.get("news", []) or []:
            keys.add((
                _normalize_headline(n.get("headline", "")),
                (n.get("source_url") or "").strip(),
            ))
    return keys


def _index_previous_metrics(previous_brief: dict[str, Any] | None) -> dict[tuple[str, str], str]:
    """Build a map of (section_slug, label) → previous value text."""
    if not previous_brief:
        return {}
    out: dict[tuple[str, str], str] = {}
    for section in previous_brief.get("sections", []):
        slug = section.get("slug", "")
        for m in section.get("metrics", []) or []:
            out[(slug, m.get("label", ""))] = m.get("value", "")
    return out


def stamp_changed(current: BriefPayloadV6, previous_brief: dict[str, Any] | None) -> None:
    """Mutate `current` in place: stamp `changed=True/False` on every news + metric.

    Rules:
    - News: changed=True if (normalized_headline, source_url) is NOT in previous brief.
    - Metric: changed=True if (slug, label) IS in previous brief AND value text differs.
              changed=True also if (slug, label) is brand new (not in previous).
              changed=False if (slug, label) matches and value text is identical.
    - When previous_brief is None: everything is changed=True (cold start).
    """
    prev_news = _index_previous_news(previous_brief)
    prev_metrics = _index_previous_metrics(previous_brief)

    for section in current.sections:
        for n in section.news:
            key = (_normalize_headline(n.headline), (n.source_url or "").strip())
            n.changed = key not in prev_news

        for m in section.metrics:
            key = (section.slug, m.label)
            if key not in prev_metrics:
                m.changed = True
            else:
                m.changed = prev_metrics[key] != m.value
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/builders/test_diff.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add brief/builders/__init__.py brief/builders/diff.py tests/builders/__init__.py tests/builders/test_diff.py tests/fixtures/v6_previous_brief.json
git commit -m "feat(builders): add stamp_changed for deterministic V6 diff signal"
```

---

### Task 2.2: `mark_held_overs` — annotate quarterly/monthly metrics

**Files:**
- Modify: `brief/builders/diff.py`
- Modify: `tests/builders/test_diff.py`
- Create: `tests/fixtures/v6_metric_definitions.json`

- [ ] **Step 1: Write the metric_definitions fixture**

`tests/fixtures/v6_metric_definitions.json`:

```json
{
  "definitions": [
    {"id": "npl_ratio", "label": "NPL Ratio", "section_slug": "banking", "cadence": "quarterly", "last_print_date": "2026-04-18"},
    {"id": "car_ratio", "label": "CAR", "section_slug": "banking", "cadence": "quarterly", "last_print_date": "2026-04-18"},
    {"id": "brent_spot", "label": "Brent Spot", "section_slug": "iran", "cadence": "daily", "last_print_date": "2026-05-05"},
    {"id": "remittance_monthly", "label": "Remittance", "section_slug": "fx", "cadence": "monthly", "last_print_date": "2026-04-30"}
  ]
}
```

- [ ] **Step 2: Add failing tests to test_diff.py**

Append to `tests/builders/test_diff.py`:

```python
from brief.builders.diff import mark_held_overs


@pytest.fixture
def metric_definitions() -> list[dict]:
    return json.loads((FIXTURES / "v6_metric_definitions.json").read_text())["definitions"]


def test_quarterly_metric_held_over_annotated(previous_brief, metric_definitions):
    """NPL 35.73% unchanged + cadence=quarterly → held_from=last_print_date, next_print computed."""
    current = _make_brief({"banking": [
        {"label": "NPL Ratio", "value": "35.73%", "changed": False}
    ]}, {})
    mark_held_overs(current, previous_brief, metric_definitions)
    m = current.sections[0].metrics[0]
    assert m.held_from is not None
    assert "Q3 2026" in (m.next_print or "") or "Jul" in (m.next_print or "")  # cadence=quarterly + last=2026-04-18 → next ≈ Jul 2026


def test_daily_metric_not_held_over(previous_brief, metric_definitions):
    """Brent (cadence=daily) — never marked held-over even if value happened to repeat."""
    current = _make_brief({"iran": [
        {"label": "Brent Spot", "value": "$107.56", "changed": False}
    ]}, {})
    mark_held_overs(current, previous_brief, metric_definitions)
    m = current.sections[0].metrics[0]
    assert m.held_from is None
    assert m.next_print is None


def test_changed_metric_not_held_over(previous_brief, metric_definitions):
    """Metric marked changed=True is by definition not held-over."""
    current = _make_brief({"banking": [
        {"label": "NPL Ratio", "value": "37.10%", "changed": True}
    ]}, {})
    mark_held_overs(current, previous_brief, metric_definitions)
    m = current.sections[0].metrics[0]
    assert m.held_from is None


def test_unknown_metric_not_held_over(previous_brief, metric_definitions):
    """Metric not in catalog → no annotation, no error."""
    current = _make_brief({"banking": [
        {"label": "Made-up Metric", "value": "42", "changed": False}
    ]}, {})
    mark_held_overs(current, previous_brief, metric_definitions)
    assert current.sections[0].metrics[0].held_from is None


def test_no_previous_brief_no_held_overs():
    """Cold start: nothing to compare → no held-overs."""
    current = _make_brief({"banking": [
        {"label": "NPL Ratio", "value": "35.73%"}
    ]}, {})
    mark_held_overs(current, None, [])
    assert current.sections[0].metrics[0].held_from is None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/builders/test_diff.py::test_quarterly_metric_held_over_annotated -v
```

Expected: ImportError on `mark_held_overs`.

- [ ] **Step 4: Implement `mark_held_overs`**

Append to `brief/builders/diff.py`:

```python
from datetime import date as date_t, timedelta
from typing import Iterable


_CADENCE_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
    "quarterly": 91,
    "annual": 365,
}

_CADENCE_LABEL: dict[str, str] = {
    "monthly": "next month",
    "quarterly": "next quarter",
    "annual": "next year",
}

_HELD_OVER_CADENCES = {"monthly", "quarterly", "annual"}


def _compute_next_print(last_print: date_t, cadence: str) -> str:
    """Return a free-text label for the next expected print, e.g. 'Jul 2026' or 'Q3 2026'."""
    days = _CADENCE_DAYS.get(cadence, 0)
    if not days:
        return _CADENCE_LABEL.get(cadence, "")
    next_date = last_print + timedelta(days=days)
    if cadence == "quarterly":
        # Tag with quarter label
        q = (next_date.month - 1) // 3 + 1
        return f"Q{q} {next_date.year} (≈ {next_date.strftime('%b %Y')})"
    if cadence == "monthly":
        return next_date.strftime("%b %Y")
    if cadence == "annual":
        return str(next_date.year)
    return next_date.isoformat()


def _index_definitions(definitions: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(section_slug, label) → catalog row."""
    return {(d.get("section_slug", ""), d.get("label", "")): d for d in definitions}


def mark_held_overs(
    current: BriefPayloadV6,
    previous_brief: dict[str, Any] | None,
    metric_definitions: Iterable[dict[str, Any]],
) -> None:
    """Mutate `current` in place: annotate held-over metrics with held_from + next_print.

    A metric is held-over if all of:
      - It exists in the previous brief at the same (slug, label)
      - Its value text is identical (i.e. changed=False)
      - Its cadence in the catalog is monthly/quarterly/annual

    Daily/weekly metrics are never held-over (they should be moving).
    """
    if not previous_brief:
        return

    catalog = _index_definitions(metric_definitions)

    for section in current.sections:
        for m in section.metrics:
            if m.changed:
                continue
            row = catalog.get((section.slug, m.label))
            if not row:
                continue
            cadence = row.get("cadence", "")
            if cadence not in _HELD_OVER_CADENCES:
                continue
            last_print_str = row.get("last_print_date")
            if not last_print_str:
                continue
            try:
                last_print = date_t.fromisoformat(last_print_str)
            except ValueError:
                continue
            m.held_from = last_print
            m.next_print = _compute_next_print(last_print, cadence)
```

- [ ] **Step 5: Run held-over tests to verify pass**

```bash
.venv/bin/python -m pytest tests/builders/test_diff.py -v
```

Expected: 12 passed (7 stamp_changed + 5 mark_held_overs).

- [ ] **Step 6: Commit**

```bash
git add brief/builders/diff.py tests/builders/test_diff.py tests/fixtures/v6_metric_definitions.json
git commit -m "feat(builders): add mark_held_overs for quarterly/monthly metric honesty"
```

---

### Task 2.3: `filter_headlines` — drop re-runs from candidate pool

**Files:**
- Create: `brief/builders/dedup.py`
- Create: `tests/builders/test_dedup.py`

- [ ] **Step 1: Write the failing test**

`tests/builders/test_dedup.py`:

```python
"""Unit tests for filter_headlines — bans re-runs against the last N issues."""
from brief.builders.dedup import filter_headlines


def test_drops_exact_match():
    """Identical headline + URL in last_5_issues_news → dropped."""
    candidates = [
        {"headline": "X happened", "source_url": "https://x.com/1"},
        {"headline": "Y happened", "source_url": "https://y.com/1"},
    ]
    last_5 = [{"headline": "X happened", "source_url": "https://x.com/1"}]
    out, dropped = filter_headlines(candidates, last_5)
    assert len(out) == 1
    assert out[0]["headline"] == "Y happened"
    assert dropped == 1


def test_drops_normalized_match():
    """Different case/punctuation but same content → dropped."""
    candidates = [{"headline": "X HAPPENED!!", "source_url": "https://x.com/1"}]
    last_5 = [{"headline": "x happened", "source_url": "https://x.com/1"}]
    out, dropped = filter_headlines(candidates, last_5)
    assert out == []
    assert dropped == 1


def test_keeps_same_headline_different_url():
    """Same headline text + different URL → kept (likely a fresh follow-up)."""
    candidates = [{"headline": "X happened", "source_url": "https://x.com/2"}]
    last_5 = [{"headline": "X happened", "source_url": "https://x.com/1"}]
    out, dropped = filter_headlines(candidates, last_5)
    assert len(out) == 1
    assert dropped == 0


def test_empty_history_keeps_all():
    """No history (cold start) → return everything unfiltered."""
    candidates = [
        {"headline": "X", "source_url": "u1"},
        {"headline": "Y", "source_url": "u2"},
    ]
    out, dropped = filter_headlines(candidates, [])
    assert len(out) == 2
    assert dropped == 0


def test_preserves_order():
    """Output order matches input order for kept items."""
    candidates = [
        {"headline": "A", "source_url": "ua"},
        {"headline": "B", "source_url": "ub"},
        {"headline": "C", "source_url": "uc"},
    ]
    last_5 = [{"headline": "B", "source_url": "ub"}]
    out, _ = filter_headlines(candidates, last_5)
    assert [x["headline"] for x in out] == ["A", "C"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/builders/test_dedup.py -v
```

Expected: 5 fail with `ImportError`.

- [ ] **Step 3: Write the implementation**

`brief/builders/dedup.py`:

```python
"""Headline re-run filter for V6 briefs.

Drops candidates whose (normalized_headline, source_url) appeared in the
last N issues. Pure function, deterministic, no LLM.
"""
from __future__ import annotations

import re
from typing import Any


_PUNCT_WHITESPACE = re.compile(r"[^\w]+")


def _normalize(text: str) -> str:
    return _PUNCT_WHITESPACE.sub("", (text or "").lower())


def _key(item: dict[str, Any]) -> tuple[str, str]:
    return (_normalize(item.get("headline", "")), (item.get("source_url") or "").strip())


def filter_headlines(
    candidates: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Return (kept_candidates, dropped_count).

    A candidate is dropped if its (normalized_headline, source_url) appears
    anywhere in `history`. Order of kept items is preserved.

    `history` is the flat union of news items from the previous N issues —
    the caller (pipeline_v6) is responsible for assembling it.
    """
    seen = {_key(h) for h in history}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for c in candidates:
        if _key(c) in seen:
            dropped += 1
            continue
        kept.append(c)
    return kept, dropped
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/builders/test_dedup.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add brief/builders/dedup.py tests/builders/test_dedup.py
git commit -m "feat(builders): add filter_headlines for re-run banning"
```

---

### Task 2.4: Push Phase 2 PR

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest --no-cov -q
```

Expected: all green.

- [ ] **Step 2: Push and open PR (Phase 2)**

This phase ships pure functions only — not yet wired into the pipeline. Open as a separate PR for review.

```bash
git push origin feat/fresh-brief
# Phase 1 PR may still be open. If merged, retarget. If not, this is now part of the same stack.
```

If the user wants the phases as separate PRs, branch off main:

```bash
git checkout main && git pull --ff-only
git checkout -b feat/fresh-brief-primitives
git cherry-pick <phase-2-commits>
git push -u origin feat/fresh-brief-primitives
gh pr create --title "feat: V1 fresh-brief — Phase 2 diff primitives" --body "Stack 2/5. Pure functions; not wired yet. See spec/plan in repo."
```

DO NOT merge autonomously. Stop and ask.

---

## Phase 3: Lens scorer

### Task 3.1: `score_lens` — pick today's lens (Mon–Thu)

**Files:**
- Create: `brief/builders/lens.py`
- Create: `tests/builders/test_lens.py`

- [ ] **Step 1: Write the failing test**

`tests/builders/test_lens.py`:

```python
"""Unit tests for score_lens — data-driven daily lens picker."""
from datetime import date

import pytest

from brief.builders.lens import score_lens


def _section(slug: str, metrics: list[dict], days_since_refresh: int = 0) -> dict:
    return {
        "slug": slug,
        "metrics": metrics,
        "freshness_days_since_refresh": days_since_refresh,
    }


def test_friday_returns_weekly_wrap_unconditionally():
    """Friday always wins weekly_wrap regardless of data."""
    sections = [_section("banking", [{"label": "NPL", "value": "35.73%", "delta_sigma": 5.0}])]
    lens, _ = score_lens(sections, today=date(2026, 5, 8), previous_lens=None)  # Friday
    assert lens == "weekly_wrap"


def test_highest_movement_wins():
    """Mon: section with the biggest σ-move wins."""
    today = date(2026, 5, 4)  # Monday
    sections = [
        _section("banking", [{"label": "NPL", "value": "35.73%", "delta_sigma": 0.0}], days_since_refresh=20),
        _section("iran",    [{"label": "Brent", "value": "$113.95", "delta_sigma": 3.2}], days_since_refresh=0),
    ]
    lens, breakdown = score_lens(sections, today=today, previous_lens="banking")
    assert lens == "iran"
    assert breakdown["iran"]["score"] > breakdown["banking"]["score"]


def test_held_over_section_loses_signal():
    """A section dominated by held-overs scores low even if data is "fresh"."""
    today = date(2026, 5, 4)
    sections = [
        _section("banking", [
            {"label": "NPL", "value": "35.73%", "delta_sigma": 0.0, "is_held_over": True},
            {"label": "CAR", "value": "1.56%", "delta_sigma": 0.0, "is_held_over": True},
        ], days_since_refresh=0),
        _section("fx", [{"label": "USDBDT", "value": "122.70", "delta_sigma": 1.5}], days_since_refresh=0),
    ]
    lens, _ = score_lens(sections, today=today, previous_lens=None)
    assert lens == "fx"


def test_quiet_day_falls_back_to_previous_lens():
    """All sections score < 0.05 → fall back to previous_lens."""
    today = date(2026, 5, 4)
    sections = [
        _section("banking", [{"label": "X", "value": "1", "delta_sigma": 0.0}], days_since_refresh=20),
    ]
    lens, breakdown = score_lens(sections, today=today, previous_lens="iran")
    assert lens == "iran"
    assert breakdown["fallback"] == "quiet_day"


def test_quiet_day_no_previous_falls_back_to_alpha():
    """Quiet day + no previous lens → alphabetical first slug."""
    today = date(2026, 5, 4)
    sections = [
        _section("zebra", [{"label": "X", "value": "1", "delta_sigma": 0.0}], days_since_refresh=20),
        _section("alpha", [{"label": "Y", "value": "2", "delta_sigma": 0.0}], days_since_refresh=20),
    ]
    lens, _ = score_lens(sections, today=today, previous_lens=None)
    assert lens == "alpha"


def test_freshness_decay_linear_14d():
    """freshness=1.0 today, 0.5 at 7d, 0.0 at >=14d."""
    from brief.builders.lens import _freshness_score
    assert _freshness_score(0) == 1.0
    assert abs(_freshness_score(7) - 0.5) < 0.01
    assert _freshness_score(14) == 0.0
    assert _freshness_score(30) == 0.0
```

- [ ] **Step 2: Run tests, expect failures**

```bash
.venv/bin/python -m pytest tests/builders/test_lens.py -v
```

Expected: 6 fail with ImportError.

- [ ] **Step 3: Implement `score_lens`**

`brief/builders/lens.py`:

```python
"""Data-driven daily lens scorer for V6 briefs.

Mon–Thu: pick the section with highest score_freshness × score_magnitude × score_signal.
Friday: lens hardcoded to "weekly_wrap".

Returns (lens_slug, breakdown_dict) for logging visibility.
"""
from __future__ import annotations

from datetime import date as date_t
from typing import Any


_QUIET_DAY_THRESHOLD = 0.05


def _freshness_score(days_since_refresh: int) -> float:
    """Linear decay: today=1.0, 7d=0.5, ≥14d=0.0."""
    if days_since_refresh < 0:
        days_since_refresh = 0
    return max(0.0, 1.0 - days_since_refresh / 14.0)


def _magnitude_score(metrics: list[dict[str, Any]]) -> float:
    """Largest |delta_sigma| in section, clamped to [0, 1]."""
    if not metrics:
        return 0.0
    best = 0.0
    for m in metrics:
        ds = abs(float(m.get("delta_sigma", 0.0) or 0.0))
        if ds > best:
            best = ds
    return min(1.0, best)


def _signal_score(metrics: list[dict[str, Any]]) -> float:
    """1 − fraction of metrics flagged is_held_over. Empty section → 0."""
    if not metrics:
        return 0.0
    held = sum(1 for m in metrics if m.get("is_held_over"))
    return 1.0 - (held / len(metrics))


def score_lens(
    sections: list[dict[str, Any]],
    *,
    today: date_t,
    previous_lens: str | None,
) -> tuple[str, dict[str, Any]]:
    """Pick today's editorial lens.

    Friday → "weekly_wrap" unconditionally.
    Mon–Thu → highest section_score = freshness × magnitude × signal.
    Quiet day (all scores < 0.05) → fall back to previous_lens, else alphabetically first slug.

    Returns (lens_slug, breakdown) where breakdown has per-section score components
    plus an optional "fallback" key.
    """
    if today.weekday() == 4:  # Friday
        return "weekly_wrap", {"reason": "friday"}

    breakdown: dict[str, Any] = {}
    for s in sections:
        slug = s["slug"]
        f = _freshness_score(int(s.get("freshness_days_since_refresh", 0) or 0))
        m = _magnitude_score(s.get("metrics", []) or [])
        sig = _signal_score(s.get("metrics", []) or [])
        score = f * m * sig
        breakdown[slug] = {"freshness": f, "magnitude": m, "signal": sig, "score": score}

    if not breakdown:
        return "banking", {"fallback": "no_sections"}

    # Find highest-scoring section
    best_slug = None
    best_score = -1.0
    for slug, b in breakdown.items():
        if b["score"] > best_score or (b["score"] == best_score and (best_slug is None or slug < best_slug)):
            best_score = b["score"]
            best_slug = slug

    if best_score < _QUIET_DAY_THRESHOLD:
        if previous_lens:
            breakdown["fallback"] = "quiet_day"
            return previous_lens, breakdown
        breakdown["fallback"] = "quiet_day_alpha"
        return sorted(breakdown.keys() - {"fallback"})[0], breakdown

    return best_slug or "banking", breakdown
```

- [ ] **Step 4: Run tests, expect pass**

```bash
.venv/bin/python -m pytest tests/builders/test_lens.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add brief/builders/lens.py tests/builders/test_lens.py
git commit -m "feat(builders): add score_lens for data-driven daily lens"
```

---

### Task 3.2: Push Phase 3 PR

Same pattern as Phase 2.4 — push, open PR, do not merge without approval.

```bash
git push origin feat/fresh-brief
gh pr create --title "feat: V1 fresh-brief — Phase 3 lens scorer" --body "Stack 3/5. Pure function; not wired yet."
```

---

## Phase 4: Mon–Thu wiring + editor prompt rewrite

This is the first user-visible phase.

### Task 4.1: Editor prompt rewrite (5 surgical changes)

**Files:**
- Modify: `brief/claude/prompts/editor_v6.txt`

The current prompt is at `brief/claude/prompts/editor_v6.txt`. Apply the five changes below using `Edit` operations against exact existing strings.

- [ ] **Step 1: Drop the NPL>30% rule**

Replace this block (around line 80–86):

```
## Hero (weight=2) selection

Exactly ONE section has `weight=2`. Pick it by this priority:
1. If `banking` section's NPL ratio is >30% AND it's a fresh-data day → banking is the lead
2. Otherwise, pick the section with the largest absolute movement vs previous brief that isn't already chronic (i.e. not already weight=2 yesterday)
3. Hero section's `cover_metric.section_slug` MUST equal that section's slug
```

With:

```
## Hero (weight=2) selection

The lens for today is supplied as `today_lens` in the input. The section whose slug matches `today_lens` is the hero. Set `weight=2` on that section and `weight=1` on all others. The cover_metric MUST come from the hero section, and MUST be a metric that is not held-over (no `held_from` annotation will be present at this point — but you must NOT pick a metric whose value text is unchanged from the previous brief's matching metric).

If `today_lens` is `weekly_wrap`, use a different prompt — you should not be reading this one on Friday.
```

- [ ] **Step 2: Headlines 4 → 12 + filter awareness**

Replace this block (around line 113):

```
## Curated headlines (headlines section)

Input gives you ~30 scraped headlines. You select and order 4. Selection criteria, in order:
1. BD-specific over global (a Bangladesh banking story beats a global oil story)
2. Today over yesterday
3. Numerical concreteness over editorializing
4. Diversify sources (don't pick 4 from DS)
5. The lead headline (news[0]) gets the densest dek (1-line `detail`)
```

With:

```
## Curated headlines (headlines section)

Input gives you a `scraped_headlines` pool. Select and order **up to 12** items from this pool. The pool has already been filtered upstream — items appearing in any of the last 5 issues have been removed. You should not see re-runs; if you do, drop them.

Selection criteria, in order:
1. BD-specific over global (a Bangladesh banking story beats a global oil story)
2. Today over yesterday
3. Numerical concreteness over editorializing
4. Diversify sources (don't pick 12 from one outlet)
5. The lead headline (news[0]) gets the densest dek (1-line `detail`)

If the filtered pool is smaller than 12, ship what you have. Do NOT pad with re-runs.
```

- [ ] **Step 3: Add today_frame instruction**

Insert after the "Hero (weight=2) selection" block (the new one from Step 1) — before the "Tone derivation" block:

```
## Today's editorial frame

The input includes `today_lens`. You must pick a `frame` from this list and set `BriefV6.frame` accordingly. The `todays_call` paragraph MUST execute the frame's analytical lens — same data, fresh angle.

| Frame | When to pick it |
|---|---|
| sovereign-debt | Government debt / fiscal pressure / refinance / budget items dominate the lens section |
| FX-runway     | Reserves / FX rate / remittance / import-cover items dominate |
| credit-cycle  | NPL / CAR / sector credit growth items dominate |
| rates-curve   | Yield curve / T-bill / T-bond / monetary policy items dominate |
| external-shock| Brent / global commodity / Iran-war / external macro items dominate |
| weekly-wrap   | Friday only — synthesizes the week. (Do not use this frame in Mon–Thu briefs.) |

`todays_call` is a 350–550 char paragraph in the Desk Editor voice that anchors the day in the chosen frame.
```

- [ ] **Step 4: Schema doc updates for system-stamped fields**

In the `OUTPUT SCHEMA — STRICT JSON` block (around line 16–23 for cover_metric, line 47–52 for metrics, line 49–52 for news), append a `// SYSTEM-STAMPED` comment to the relevant fields. Example for `metrics`:

Replace:

```
      "metrics": [
        // Pass through the metrics from input data unchanged in shape, but you MAY:
        //  - reorder so the most newsworthy is first
        //  - set 'tone' if input lacked it
        //  - drop low-signal metrics (max 5 per section)
        { "label": "...", "value": "...", "sub": "...", "tone": "...", "weight": 1|2, ... }
      ],
```

With:

```
      "metrics": [
        // Pass through the metrics from input data unchanged in shape, but you MAY:
        //  - reorder so the most newsworthy is first
        //  - set 'tone' if input lacked it
        //  - drop low-signal metrics (max 5 per section)
        // DO NOT set `changed`, `held_from`, or `next_print` — those are SYSTEM-STAMPED post-LLM.
        { "label": "...", "value": "...", "sub": "...", "tone": "...", "weight": 1|2, ... }
      ],
```

Apply the same SYSTEM-STAMPED note to the news block and the cover_metric block.

In the brief block (around line 11–25), add `lens` and `frame` as required output fields:

```
  "brief": {
    "issue_no":      <int>,
    "volume":        <int>,
    "brief_date":    "YYYY-MM-DD",
    "read_minutes":  <int 7..12>,
    "lens":          "<copy from input today_lens>",
    "frame":         "<one of: sovereign-debt|FX-runway|credit-cycle|rates-curve|external-shock>",
    "cover_metric": { ... },
    "todays_call":   "...",
    "status":        "published"
  },
```

- [ ] **Step 5: Stale-data tightening**

Replace the existing block (around line 104–110):

```
## Stale data handling

The input flags each section's freshness state ('fresh', 'warning', 'stale', 'unavailable'). When a section is `stale` or worse:
- banker_read.verdict must acknowledge it implicitly ('On the last print...' / 'Pending Q1 disclosure...')
- DON'T claim 'today' or 'this week' for stale data
- summary_pills can still display the stale value but with `tone="warn"` if the value is stale-bear or stale-warn
- If freshness is `unavailable`: omit banker_read, set verdict to "Data pending — see <next print date>", verdict_tone="neu"
```

With:

```
## Stale data handling

The input flags each section's freshness state ('fresh', 'warning', 'stale', 'unavailable'). When a section is `stale` or worse:
- banker_read.verdict MUST acknowledge it explicitly with the *exact* phrase "Held from <date>" if the system can compute one — but YOU don't compute the date; just refer to the held nature: "On the last print (Q4 2025)…"
- DON'T claim 'today' or 'this week' for stale data
- DON'T pretend a quarterly metric is news. The reader will see a "Held from" footer post-LLM; do not contradict it.
- summary_pills can still display the stale value but with `tone="warn"` if the value is stale-bear or stale-warn
- If freshness is `unavailable`: omit banker_read, set verdict to "Data pending — see <next print date>", verdict_tone="neu"
```

- [ ] **Step 6: Add today_lens to INPUT DATA section**

Replace (around line 122–127):

```
The input JSON below has these top-level keys:
- `today`: ISO date string
- `previous_brief`: yesterday's published brief (or null if first run); use for diff signaling and hero rotation
- `sections_raw`: array of section build outputs from the deterministic builders. Each has slug/ord/title/group_key/freshness/metrics/news/series/notes. Pass-through fields: ord, slug, title, group_key, series, notes.
- `scraped_headlines`: pool of ~30 candidate headlines for the headlines section
- `meta`: { issue_no, volume, brief_date }
```

With:

```
The input JSON below has these top-level keys:
- `today`: ISO date string
- `today_lens`: the slug of today's hero section (e.g. "banking", "iran", "fx"). Pre-computed by a deterministic scorer; you MUST honor it.
- `previous_brief`: yesterday's published brief (or null if first run); use for hero context (NOT for diff signaling — that is system-stamped post-LLM)
- `sections_raw`: array of section build outputs from the deterministic builders. Each has slug/ord/title/group_key/freshness/metrics/news/series/notes. Pass-through fields: ord, slug, title, group_key, series, notes.
- `scraped_headlines`: pool of candidate headlines for the headlines section, already filtered upstream against the last 5 issues.
- `meta`: { issue_no, volume, brief_date }
```

- [ ] **Step 7: Commit prompt changes**

```bash
git add brief/claude/prompts/editor_v6.txt
git commit -m "feat(prompt): rewrite editor_v6 for fresh-brief — lens, frame, headlines=12, system-stamped fields"
```

---

### Task 4.2: Wire builders into pipeline_v6.py

**Files:**
- Modify: `brief/pipeline_v6.py`
- Modify: `brief/v6_publisher.py` (one helper added: `fetch_recent_news(n_issues)`)

- [ ] **Step 1: Add `fetch_recent_news` to v6_publisher.py**

Add to `brief/v6_publisher.py` after `fetch_previous_brief()`:

```python
def fetch_recent_news(n_issues: int = 5) -> list[dict[str, Any]]:
    """Return the flat list of news items from the most recent N published briefs.

    Used by filter_headlines() to dedupe today's candidate pool against the
    last work-week of news.
    """
    briefs = _request(
        "GET",
        f"/briefs?status=eq.published&order=brief_date.desc&limit={n_issues}&select=id",
    ) or []
    if not briefs:
        return []
    brief_ids = ",".join(b["id"] for b in briefs)
    sections = _request(
        "GET",
        f"/sections?brief_id=in.({brief_ids})&select=id",
    ) or []
    if not sections:
        return []
    section_ids = ",".join(s["id"] for s in sections)
    news = _request(
        "GET",
        f"/news?section_id=in.({section_ids})&select=headline,source_url",
    ) or []
    return news
```

- [ ] **Step 2: Modify `_build_editor_input` in pipeline_v6.py**

The new shape pre-computes `today_lens`, filters scraped_headlines, and passes today_lens through.

Replace `_build_editor_input` (around line 80–97):

```python
def _build_editor_input(
    sections: list[SectionData],
    today: date_t,
    scraped_headlines: list[dict[str, Any]],
    *,
    previous_brief: dict[str, Any] | None,
    previous_lens: str | None,
    recent_news: list[dict[str, Any]],
    metric_definitions: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    """Build editor input + return chosen lens.

    Returns (editor_input, today_lens). Caller passes today_lens to the
    appropriate prompt template; mostly relevant when caller wants to log it.
    """
    from brief.builders.lens import score_lens
    from brief.builders.dedup import filter_headlines

    next_issue = fetch_max_issue_no() + 1
    raw_sections = _to_v6_raw(sections)

    # Compute today's lens
    sections_for_lens = [
        {
            "slug": s["slug"],
            "freshness_days_since_refresh": _days_since_refresh(s.get("freshness")),
            "metrics": [
                {
                    "label": m["label"],
                    "value": m["value"],
                    "delta_sigma": _delta_sigma(m, metric_definitions),
                    "is_held_over": False,  # cannot know yet — that's a post-LLM annotation
                }
                for m in s.get("metrics", []) or []
            ],
        }
        for s in raw_sections
    ]
    lens, lens_breakdown = score_lens(sections_for_lens, today=today, previous_lens=previous_lens)

    # Filter scraped headlines against last 5 issues
    filtered_headlines, dropped = filter_headlines(scraped_headlines, recent_news)
    if dropped:
        logger.info("v6: filter_headlines dropped %d re-runs", dropped)

    return {
        "today": today.isoformat(),
        "today_lens": lens,
        "previous_brief": previous_brief,
        "scraped_headlines": filtered_headlines,
        "sections_raw": raw_sections,
        "meta": {
            "issue_no": next_issue,
            "volume": (previous_brief or {}).get("brief", {}).get("volume", 1),
            "brief_date": today.isoformat(),
        },
    }, lens
```

Add the two helpers below it:

```python
def _days_since_refresh(freshness: str | None) -> int:
    """Map V5's freshness label to a days-since-refresh number for the lens scorer.

    'fresh' → 0 (today), 'warning' → 5, 'stale' → 14, 'unavailable' → 30.
    """
    return {"fresh": 0, "warning": 5, "stale": 14, "unavailable": 30}.get(freshness or "stale", 14)


def _delta_sigma(metric: dict[str, Any], definitions: list[dict[str, Any]]) -> float:
    """Best-effort σ-move estimate. If the metric carries delta_pct, use abs(delta_pct).

    For a real V1 ship we could compute σ from metric_history. For now, abs(delta_pct/2)
    as a proxy — small moves score low, big moves score high. Returns 0 if no signal.
    """
    delta_pct = metric.get("delta_pct") or ""
    try:
        return abs(float(delta_pct.strip("%+")) / 2.0)
    except (ValueError, TypeError):
        return 0.0
```

- [ ] **Step 3: Modify `run_publish` to wire stamp + held-overs post-LLM**

Replace `run_publish` (around line 127–209):

```python
def run_publish(
    sections: list[SectionData],
    today: date_t,
    *,
    scraped_headlines: list[dict[str, Any]] | None = None,
    dry_run: bool = False,
) -> str | None:
    """Execute the 2-call publish flow with fresh-brief V1 wiring.

    Pipeline shape:
      1. Compute today_lens (data-driven Mon–Thu, weekly_wrap on Friday)
      2. Filter scraped_headlines against last 5 issues
      3. Editor LLM produces brief
      4. Subeditor LLM reviews
      5. stamp_changed (post-LLM diff)
      6. mark_held_overs (post-LLM honesty)
      7. Publish to Supabase
    """
    from brief.builders.diff import stamp_changed, mark_held_overs

    previous = fetch_previous_brief()
    previous_lens = (previous or {}).get("brief", {}).get("lens")
    recent_news = fetch_recent_news(n_issues=5)
    metric_definitions = _request("GET", "/metric_definitions?select=id,label,section_slug,cadence,last_print_date") or []

    editor_input, today_lens = _build_editor_input(
        sections,
        today,
        scraped_headlines or [],
        previous_brief=previous,
        previous_lens=previous_lens,
        recent_news=recent_news,
        metric_definitions=metric_definitions,
    )

    issue_no = editor_input["meta"]["issue_no"]
    logger.info(
        "v6: issue_no=%d, %d sections raw, lens=%s",
        issue_no, len(editor_input["sections_raw"]), today_lens,
    )

    # ── Friday branch ──────────────────────────────────────────────
    is_friday = today.weekday() == 4
    if is_friday:
        from brief.builders.weekly import build_weekly_input
        editor_input = build_weekly_input(editor_input, today)
        editor_prompt_file = "editor_v6_friday.txt"
    else:
        editor_prompt_file = "editor_v6.txt"

    # ── Call 1: Editor ─────────────────────────────────────────────
    editor_prompt = _pipeline._load_prompt(editor_prompt_file).replace("{today}", today.isoformat())
    editor_raw = _call_with_retries(
        label="editor_v6", prompt_template=editor_prompt, input_obj=editor_input, timeout_s=1800,
    )
    try:
        editor_brief = BriefPayloadV6.model_validate(editor_raw)
    except Exception as e:
        raise V6PublishError(f"editor_v6 output failed schema validation: {e}") from e

    # Force lens onto the brief — the LLM should set it but we guarantee it
    editor_brief.brief.lens = today_lens

    logger.info(
        "v6: editor produced brief with %d sections, hero=%s, frame=%s",
        len(editor_brief.sections),
        next((s.slug for s in editor_brief.sections if s.weight == 2), None),
        editor_brief.brief.frame,
    )

    # ── Call 2: Sub-editor ─────────────────────────────────────────
    subeditor_prompt = _pipeline._load_prompt("subeditor_v6.txt")
    subeditor_input = {"editor_output": editor_brief.model_dump(mode="json"), "raw_data": editor_input}
    review_raw = _call_with_retries(
        label="subeditor_v6", prompt_template=subeditor_prompt, input_obj=subeditor_input, timeout_s=1800,
    )
    try:
        review = SubeditorReview.model_validate(review_raw)
    except Exception as e:
        logger.warning("v6: subeditor output failed schema validation, passing editor output: %s", e)
        review = SubeditorReview(verdict="pass")

    if review.verdict == "fail":
        msgs = [f"  · [{i.severity}] {i.section}.{i.field}: {i.problem}" for i in review.issues]
        raise V6PublishError(f"subeditor verdict=fail with {len(review.issues)} issues:\n" + "\n".join(msgs))

    if review.verdict == "revise" and review.revised_brief is not None:
        final_brief = review.revised_brief
        # Re-force lens on revised brief
        final_brief.brief.lens = today_lens
        logger.info("v6: subeditor revised brief, %d issues fixed", len(review.issues))
    else:
        final_brief = editor_brief
        if review.issues:
            logger.info("v6: subeditor passed with %d warnings", len(review.issues))
        else:
            logger.info("v6: subeditor passed clean")

    # ── Post-LLM: deterministic diff + held-over stamping ──────────
    stamp_changed(final_brief, previous)
    mark_held_overs(final_brief, previous, metric_definitions)
    logger.info(
        "v6: stamp_changed + mark_held_overs done; changed_news=%d, held_metrics=%d",
        sum(1 for s in final_brief.sections for n in s.news if n.changed),
        sum(1 for s in final_brief.sections for m in s.metrics if m.held_from),
    )

    if dry_run:
        logger.info("v6: dry_run=True, skipping Supabase publish")
        return None

    try:
        return publish_brief(final_brief)
    except PublishError as e:
        raise V6PublishError(f"Supabase publish failed: {e}") from e
```

- [ ] **Step 4: Update v6_publisher.publish_brief to write new columns**

The publisher already serializes via `model_dump(mode="json")` — the new fields (`held_from`, `next_print`, `lens`, `frame`) will flow through automatically because the schema models include them. **Verify** by reading `brief/v6_publisher.py` lines 138–149 and 173–177; no change should be needed if `model_dump` is unrestricted there.

- [ ] **Step 5: Run all unit tests**

```bash
.venv/bin/python -m pytest --no-cov -q
```

Expected: all green (the new wiring didn't break existing tests).

- [ ] **Step 6: Add an integration test for Mon–Thu happy path**

Create `tests/test_pipeline_v6_freshness.py`:

```python
"""Integration-shaped test for fresh-brief V1 wiring on Mon–Thu.

Mocks Claude + Supabase; verifies the pipeline:
  - Calls score_lens with today's sections
  - Filters scraped_headlines against recent_news
  - Forces lens onto editor_brief
  - Calls stamp_changed and mark_held_overs post-LLM
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from brief import pipeline_v6
from brief.schema import SectionData
from brief.v6_schema import BriefPayloadV6, BriefV6, SectionV6, MetricV6, NewsItemV6


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def previous_brief():
    return json.loads((FIXTURES / "v6_previous_brief.json").read_text())


@pytest.fixture
def metric_definitions():
    return json.loads((FIXTURES / "v6_metric_definitions.json").read_text())["definitions"]


def _make_editor_output(today_lens="iran") -> dict:
    return {
        "brief": {
            "issue_no": 92, "volume": 1, "brief_date": "2026-05-04",
            "lens": today_lens, "frame": "external-shock",
            "todays_call": "Brent jumped...",
            "cover_metric": {"label": "BRENT", "value": "$113.95", "section_slug": "iran"},
            "status": "published",
        },
        "sections": [
            {
                "slug": "iran", "ord": 10, "title": "External", "group_key": "policy", "weight": 2,
                "metrics": [{"label": "Brent Spot", "value": "$113.95"}],
                "news": [{"headline": "Hormuz reescalation", "source_url": "https://x.com/hormuz"}],
            }
        ],
    }


def test_monday_pipeline_wires_lens_and_stamps(previous_brief, metric_definitions, monkeypatch):
    monday = date(2026, 5, 4)

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: previous_brief)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 91)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?", "source_url": "https://example.com/refinance"}
    ])
    monkeypatch.setattr(pipeline_v6, "_request", lambda method, path: metric_definitions if "metric_definitions" in path else [])
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload: "fake-uuid-123")

    fake_sections = [
        SectionData(id="iran", title="External", kicker="", tldr="", pull="",
                    freshness="fresh", freshness_reason="",
                    metrics=[], news=[]),
    ]

    scraped = [
        {"headline": "Will cenbank's Tk40,000cr refinance scheme fuel inflation?", "source_url": "https://example.com/refinance"},  # repeat
        {"headline": "Brent jumps to $113.95", "source_url": "https://example.com/brent"},  # fresh
    ]

    with patch("brief.pipeline_v6._call_with_retries") as call_mock:
        call_mock.side_effect = [
            _make_editor_output(today_lens="iran"),  # editor
            {"verdict": "pass", "issues": []},        # subeditor
        ]
        result = pipeline_v6.run_publish(
            fake_sections, today=monday, scraped_headlines=scraped, dry_run=False,
        )

    assert result == "fake-uuid-123"
    # Lens forced onto the brief
    editor_call = call_mock.call_args_list[0]
    editor_input = editor_call.kwargs["input_obj"]
    assert editor_input["today_lens"] == "iran"
    # Re-runs filtered out — only Brent headline remains
    assert len(editor_input["scraped_headlines"]) == 1
    assert "Brent" in editor_input["scraped_headlines"][0]["headline"]
```

- [ ] **Step 7: Run integration test**

```bash
.venv/bin/python -m pytest tests/test_pipeline_v6_freshness.py -v
```

Expected: 1 passed.

- [ ] **Step 8: Commit pipeline wiring**

```bash
git add brief/pipeline_v6.py brief/v6_publisher.py tests/test_pipeline_v6_freshness.py
git commit -m "feat(pipeline): wire score_lens + filter + stamp + held-overs into Mon–Thu V6 publish"
```

---

### Task 4.3: Push Phase 4 PR (USER-VISIBLE FLIP)

This phase, when merged, changes Mon–Thu publish behavior live. **Stop and discuss with user before merging.**

```bash
git push origin feat/fresh-brief
gh pr create --title "feat: V1 fresh-brief — Phase 4 Mon–Thu wiring (USER-VISIBLE)" --body "Stack 4/5. Activates lens scorer, dedup, post-LLM stamping. Mon–Thu briefs get fresh."
```

Stop here. Ask user before merging.

---

## Phase 5: Friday wrap + SPA polish

### Task 5.1: Friday weekly-wrap input builder

**Files:**
- Create: `brief/builders/weekly.py`
- Create: `tests/builders/test_weekly.py`

- [ ] **Step 1: Write failing test**

`tests/builders/test_weekly.py`:

```python
"""Unit tests for build_weekly_input — Friday weekly wrap."""
from datetime import date

from brief.builders.weekly import build_weekly_input


def test_adds_weekly_diffs_block():
    base = {
        "today": "2026-05-08",
        "today_lens": "weekly_wrap",
        "previous_brief": None,
        "sections_raw": [{"slug": "iran", "metrics": [{"label": "Brent", "value": "$113.95"}]}],
        "scraped_headlines": [],
        "meta": {"issue_no": 95, "volume": 1, "brief_date": "2026-05-08"},
    }
    out = build_weekly_input(base, today=date(2026, 5, 8))
    assert "weekly_diffs" in out
    assert out["today_lens"] == "weekly_wrap"
    # All other keys preserved
    assert out["meta"] == base["meta"]


def test_today_must_be_friday():
    """build_weekly_input on non-Friday is a programmer error — raise."""
    import pytest
    with pytest.raises(ValueError, match="Friday"):
        build_weekly_input({}, today=date(2026, 5, 4))  # Monday
```

- [ ] **Step 2: Implement**

`brief/builders/weekly.py`:

```python
"""Friday weekly-wrap input builder.

Augments the standard editor input with a `weekly_diffs` block: Mon–Fri
section deltas, biggest-σ-mover, sectoral verdicts. The Friday editor
prompt consumes this block to produce a 5-day synthesis.
"""
from __future__ import annotations

from datetime import date as date_t, timedelta
from typing import Any


def build_weekly_input(base_input: dict[str, Any], *, today: date_t) -> dict[str, Any]:
    """Take the standard editor_input and add a `weekly_diffs` block for Friday.

    For V1, weekly_diffs is a placeholder block that summarizes today's sections
    only — the Friday prompt instructs the editor to synthesize across Mon–Fri
    using its own context. A V2 enhancement could fetch Mon–Thu briefs from
    Supabase and compute exact per-day deltas; for V1 we rely on the editor's
    access to previous_brief plus its instruction to write a wrap.
    """
    if today.weekday() != 4:
        raise ValueError(f"build_weekly_input called on non-Friday: {today} (weekday={today.weekday()})")

    out = dict(base_input)
    out["today_lens"] = "weekly_wrap"
    out["weekly_diffs"] = {
        "week_of": (today - timedelta(days=today.weekday())).isoformat(),
        "today": today.isoformat(),
        "note": "Synthesize across Mon–Fri using your access to previous_brief and the sections in this input. Highlight biggest movers of the week.",
    }
    return out
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/builders/test_weekly.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add brief/builders/weekly.py tests/builders/test_weekly.py
git commit -m "feat(builders): add build_weekly_input for Friday wrap"
```

---

### Task 5.2: Friday editor prompt

**Files:**
- Create: `brief/claude/prompts/editor_v6_friday.txt`

- [ ] **Step 1: Write the prompt**

Substantial document — write the full content. Drafted below; an executing agent should refine wording/voice but preserve the structural rules.

```
You are the Desk Editor of THE BRIEF, writing FRIDAY's weekly wrap. Your job today is different from Mon–Thu: produce a 5-day synthesis, not a daily snapshot. The reader wants to know "what mattered this week" and "what to watch next week."

# OUTPUT SCHEMA

Same JSON envelope as the Mon–Thu prompt, with these structural changes:

- `brief.lens` = "weekly_wrap"
- `brief.frame` = "weekly-wrap"
- `brief.todays_call` is the WEEKLY WRAP — 5 paragraphs, ~600–900 chars total:
    Paragraph 1: macro arc (banking + sovereign + fiscal) for the week
    Paragraph 2: markets arc (rates, FX, DSE) for the week
    Paragraph 3: external arc (Brent, geopolitics) for the week
    Paragraph 4: biggest movers — name 3 metrics with biggest σ-moves and quote the numbers
    Paragraph 5: next week's watch list — 2–3 specific data prints, events, or risk vectors
- `brief.cover_metric` = the single biggest σ-mover of the week (not today's pick)
- Sections each get a one-line `verdict` that reads across the WHOLE WEEK ("Bear case strengthens — NPL stalls, CAR shrinks.")
- Hero (weight=2) section = the section containing the biggest mover

# RULES

1. Synthesize, don't recap. Don't list every event chronologically. Pick the throughline.
2. Numbers must be week-anchored: "Brent +$5.40 over the week" not "Brent at $113.95 today".
3. Voice unchanged from Mon–Thu — em-dashes, declarative, banker-to-banker.
4. Everything else (verdict, banker_read, summary_pills, analysis, news) follows the Mon–Thu prompt's rules.

# INPUT

Same as Mon–Thu plus:
- `weekly_diffs`: marker that this is a Friday wrap. Use your access to `previous_brief` to reach into earlier briefs of the week.

# RETURN

ONLY the JSON object. First char `{`, last char `}`. No prose, no markdown fences.
```

- [ ] **Step 2: Commit**

```bash
git add brief/claude/prompts/editor_v6_friday.txt
git commit -m "feat(prompt): add editor_v6_friday for weekly wrap"
```

---

### Task 5.3: SPA — three-state Section rendering

**Files:**
- Modify: `app/components/Section.tsx`
- Modify: `app/globals.css`

- [ ] **Step 1: Read current Section.tsx**

Use Read to view current state. Note the lines (36, 92–116, 134–141) where `n.changed`/`m.changed` checks live.

- [ ] **Step 2: Update news rendering**

Replace the existing news block (around line 92–101) with:

```tsx
<div
  key={i}
  className={
    n.changed
      ? "tb-news-item is-changed"
      : n.held_from
      ? "tb-news-item is-held-over"
      : "tb-news-item"
  }
>
  <div className="tb-news-headline">{n.headline}</div>
  {n.detail && <div className="tb-news-detail">{n.detail}</div>}
  <div className="tb-news-meta">
    {n.source}
    {n.changed ? " · NEW" : ""}
    {n.held_from && !n.changed ? ` · Held from ${n.held_from}` : ""}
  </div>
</div>
```

Repeat the same change at the second news rendering site (around line 134–141).

- [ ] **Step 3: Update metric rendering (around line 110–117)**

```tsx
<div
  className={
    m.changed
      ? "tb-kpi-row is-changed"
      : m.held_from
      ? "tb-kpi-row is-held-over"
      : "tb-kpi-row"
  }
>
  {/* existing inner content unchanged */}
  {m.changed && (
    <span className="tb-changed-dot" title="Updated since yesterday" />
  )}
  {m.held_from && !m.changed && (
    <span className="tb-held-footer">
      Held from {m.held_from}{m.next_print ? ` · next print ${m.next_print}` : ""}
    </span>
  )}
</div>
```

- [ ] **Step 4: Update CSS in app/globals.css**

After the existing `.tb-changed-dot` and `body.tb-diff` rules (around line 661–705), add:

```css
.tb-news-item.is-held-over,
.tb-kpi-row.is-held-over {
  opacity: 0.65;
}

.tb-held-footer {
  font-size: 0.75rem;
  color: var(--color-muted, #888);
  margin-left: 0.5rem;
  font-style: italic;
}

/* Diff toggle: held-over items shown muted, NOT blanked */
body.tb-diff .tb-section .tb-news-item.is-held-over,
body.tb-diff .tb-section .tb-kpi-row.is-held-over {
  opacity: 0.5;
  /* keep visible; don't apply the blanking rule */
}
```

And update the existing rule that hides `:not(.is-changed)` to also exclude `.is-held-over`:

```css
body.tb-diff .tb-section .tb-news-item:not(.is-changed):not(.is-held-over),
body.tb-diff .tb-section .tb-kpi-row:not(.is-changed):not(.is-held-over),
body.tb-diff .tb-cover-line:not(.is-changed):not(.is-held-over) {
  /* existing blanking treatment */
}
```

- [ ] **Step 5: Run pnpm typecheck + tests**

```bash
pnpm tsc --noEmit
pnpm test --run
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/components/Section.tsx app/globals.css
git commit -m "feat(spa): render three-state diff (changed | held-over | default)"
```

---

### Task 5.4: SPA — masthead lens pill

**Files:**
- Create: `app/components/MastheadLensPill.tsx`
- Modify: `app/components/Masthead.tsx` (existing)

- [ ] **Step 1: Read Masthead.tsx to find mount point**

Use Read to view current Masthead.tsx structure.

- [ ] **Step 2: Create MastheadLensPill.tsx**

```tsx
type Props = {
  lens?: string;
  frame?: string;
  briefDate: string; // ISO
};

const LENS_LABEL: Record<string, string> = {
  banking: "banking lens",
  fx: "FX lens",
  dse: "markets lens",
  tbond: "rates lens",
  macro: "macro lens",
  iran: "external lens",
  weekly_wrap: "weekly wrap",
};

const WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function MastheadLensPill({ lens, frame, briefDate }: Props) {
  if (!lens) return null;
  const day = WEEKDAY[new Date(briefDate).getDay() === 0 ? 6 : new Date(briefDate).getDay() - 1];
  const lensLabel = LENS_LABEL[lens] ?? lens;
  return (
    <div className="tb-masthead-lens-pill" aria-label={`Lens: ${lensLabel}`}>
      <span className="tb-mlp-day">{day}</span>
      <span className="tb-mlp-sep"> · </span>
      <span className="tb-mlp-lens">{lensLabel}</span>
      {frame && lens !== "weekly_wrap" && (
        <>
          <span className="tb-mlp-sep"> · </span>
          <span className="tb-mlp-frame">{frame.replace("-", " ")} frame</span>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Mount in Masthead.tsx**

Pass `lens`, `frame`, and `briefDate` props through and render `<MastheadLensPill />` near the date line. Exact insertion depends on the existing component shape — Read first.

- [ ] **Step 4: CSS**

Append to `app/globals.css`:

```css
.tb-masthead-lens-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border-radius: 999px;
  background: var(--color-surface-2, #f4f4f4);
  font-size: 0.75rem;
  color: var(--color-muted, #666);
  text-transform: lowercase;
  letter-spacing: 0.02em;
}

.tb-masthead-lens-pill .tb-mlp-day {
  font-weight: 600;
  text-transform: uppercase;
}
```

- [ ] **Step 5: Typecheck + test**

```bash
pnpm tsc --noEmit
pnpm test --run
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/components/MastheadLensPill.tsx app/components/Masthead.tsx app/globals.css
git commit -m "feat(spa): add masthead lens pill"
```

---

### Task 5.5: Friday integration test

**Files:**
- Create: `tests/test_pipeline_v6_friday.py`

- [ ] **Step 1: Write test**

```python
"""Friday branch test — verifies pipeline_v6 routes to editor_v6_friday on Fri."""
from datetime import date
from unittest.mock import patch

import pytest

from brief import pipeline_v6
from brief.schema import SectionData


def test_friday_uses_friday_prompt(monkeypatch):
    friday = date(2026, 5, 8)  # Friday

    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_max_issue_no", lambda: 95)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "_request", lambda method, path: [])
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload: "fake-uuid-friday")

    fake_sections = [SectionData(
        id="iran", title="External", kicker="", tldr="", pull="",
        freshness="fresh", freshness_reason="", metrics=[], news=[],
    )]

    fake_editor_out = {
        "brief": {"issue_no": 96, "volume": 1, "brief_date": "2026-05-08",
                  "lens": "weekly_wrap", "frame": "weekly-wrap",
                  "todays_call": "Wrap...", "status": "published",
                  "cover_metric": {"label": "X", "value": "y", "section_slug": "iran"}},
        "sections": [{"slug": "iran", "ord": 10, "title": "External", "group_key": "policy", "weight": 2}],
    }

    with patch("brief.pipeline_v6._call_with_retries") as call_mock, \
         patch("brief.pipeline_v6._pipeline._load_prompt") as load_prompt:
        call_mock.side_effect = [fake_editor_out, {"verdict": "pass", "issues": []}]
        load_prompt.return_value = "FAKE_PROMPT_BODY"
        result = pipeline_v6.run_publish(fake_sections, today=friday, dry_run=False)

    assert result == "fake-uuid-friday"
    # Verify Friday prompt was loaded
    prompt_files_loaded = [c.args[0] for c in load_prompt.call_args_list]
    assert "editor_v6_friday.txt" in prompt_files_loaded
    # Verify weekly_diffs block was added
    editor_call_input = call_mock.call_args_list[0].kwargs["input_obj"]
    assert "weekly_diffs" in editor_call_input
    assert editor_call_input["today_lens"] == "weekly_wrap"
```

- [ ] **Step 2: Run**

```bash
.venv/bin/python -m pytest tests/test_pipeline_v6_friday.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pipeline_v6_friday.py
git commit -m "test: add Friday branch integration test"
```

---

### Task 5.6: Push Phase 5 PR + final smoke test

- [ ] **Step 1: Run full suite**

```bash
.venv/bin/python -m pytest --no-cov -q
pnpm test --run
pnpm tsc --noEmit
```

Expected: all green.

- [ ] **Step 2: Push and open PR**

```bash
git push origin feat/fresh-brief
gh pr create --title "feat: V1 fresh-brief — Phase 5 Friday + SPA" --body "Stack 5/5. Friday wrap path; SPA three-state diff + lens pill."
```

- [ ] **Step 3: Stop and ask user for merge approval**

Same as prior phases — do not autonomously merge.

---

## Self-review

Before declaring this plan done, the writing-plans skill mandates a fresh-eyes pass:

**Spec coverage check** — Each spec section maps to tasks:

| Spec section | Plan tasks |
|---|---|
| Directive A — ban headline re-runs | Task 2.3 (filter_headlines), Task 4.2 step 2 (wires it in), recent_news fetcher Task 4.2 step 1 |
| Directive B — data-driven lens (Mon–Thu) + Friday wrap | Task 3.1 (score_lens), Task 4.2 step 2-3 (Mon–Thu wiring), Task 5.1–5.2 + 5.5 (Friday) |
| Directive C — mark held-overs | Task 2.2 (mark_held_overs), Task 4.2 step 3 (wired post-LLM), Task 5.3 (SPA render) |
| Directive D — stamp `changed` flags | Task 2.1 (stamp_changed), Task 4.2 step 3 (wired post-LLM), Task 5.3 (SPA already renders is-changed) |
| Directive E — rotate editorial frame | Task 4.1 step 3 (frame instruction in prompt), schema gains `frame` field in Phase 1, Task 5.4 (lens pill shows frame) |
| Schema migrations | Task 1.1 |
| Pydantic field additions | Task 1.2 |
| TS types | Task 1.3 |
| Editor prompt rewrite (Mon–Thu) | Task 4.1 |
| Friday prompt | Task 5.2 |
| SPA three-state | Task 5.3 |
| Lens pill | Task 5.4 |
| Tests | Each task includes its own |
| First-run/cold-start | covered by `stamp_changed` test (test_no_previous_brief_marks_everything_true), `mark_held_overs` test (test_no_previous_brief_no_held_overs), `score_lens` quiet-day fallback test |
| Quiet-day fallback | Task 3.1 step 1, test_quiet_day_falls_back_to_previous_lens |

No spec section is unmapped.

**Placeholder scan** — Searched for "TBD", "TODO", "implement later", "fill in details", "appropriate error handling", "similar to Task N". All instances are either in shell HEREDOC commit messages (legit) or in spec/plan body referring to V2 deferrals (legit). No placeholders inside step bodies.

**Type consistency** — `score_lens` returns `tuple[str, dict]` everywhere. `stamp_changed` and `mark_held_overs` mutate in place and return `None` everywhere. `filter_headlines` returns `tuple[list, int]` everywhere. `BriefV6.lens` and `.frame` are `Optional[str]` in Pydantic and `string | undefined` in TS. Names match between phases.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-05-fresh-brief.md`.**

Per user-memory `feedback_execution_mode.md`, default to **subagent-driven development**.

**Next step:** invoke `superpowers:subagent-driven-development` and execute Phase 0 → Phase 1 → … → Phase 5, with PR-merge-approval gates between phases.
