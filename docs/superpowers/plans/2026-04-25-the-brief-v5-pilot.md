# The Brief V5 — Pilot + Chrome Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working V5 pilot for the `bb` (Bangladesh Bank / Policy & Rates) section plus all front-of-book chrome (live banner, masthead, today's call, risk map, secondary grid, colophon) plus all 6 editorial Claude calls. Other 13 sections continue rendering in V4 via the `BRIEF_RENDERER` env flag — mixed-mode editions are valid output.

**Architecture:** New `brief/render/v5/` package alongside `brief/render/v4/`. V4 untouched. Schema additions are back-compatible. Pipeline reads `BRIEF_RENDERER=v5` flag and dispatches to V5 chrome + V5 templates for sections present in the V5 templates dir; falls back to V4 templates for any section not yet ported. Spec authority: `docs/superpowers/specs/2026-04-25-the-brief-v5-design.md`.

**Tech Stack:** Python 3.13, Pydantic 2.13, Claude Max CLI (`claude-opus-4-7` with extended thinking), pytest, urllib HTTP client, deterministic Python renderer (no JS framework), CSS variables for design tokens.

**Out of scope for Plan A:** the 13 non-pilot sections' V5 templates (those land in Plan B written after pilot validation). Mobile responsive, dark mode, email-specific V5 template, PDF export.

---

## Pre-flight: clean working state

- [ ] **Step 1: Verify branch + clean tree**

Run: `cd ~/Projects/clauding-lab/the-brief && git status --short && git branch --show-current`
Expected: clean tree, branch `feat/v4-retarget` (or whatever V4 lives on; do not branch from `main` — V4 hasn't been promoted yet).

- [ ] **Step 2: Cut V5 working branch**

Run: `git checkout -b feat/v5-pilot feat/v4-retarget`
Expected: switched to a new branch `feat/v5-pilot`.

- [ ] **Step 3: Verify suite is green at the V4 baseline**

Run: `source .venv/bin/activate && pytest -q 2>&1 | tail -3`
Expected: `521 passed` (or whatever the current count is — record this number; new tests must net add to it without losing any).

---

## Phase 1 — Schema additions (~30 min)

**Files:**
- Modify: `brief/schema.py`
- Test: `tests/test_schema.py` (add to existing file)

### Task 1: Add V5 fields to schema

- [ ] **Step 1: Write failing test for new V5 schema additions**

Add to `tests/test_schema.py`:

```python
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from brief.schema import (
    BankerReadInsight,
    GridEntry,
    MapPoint,
    QAIssue,
    EditorialQAResult,
    SectionData,
    SystemicRisk,
    TodaysCall,
    TopPicks,
)


def test_systemic_risk_validates():
    risk = SystemicRisk(
        headline="NPL ratio at world high",
        body="x" * 80,
        level="critical",
        rule_id="banking_npl_above_30",
    )
    assert risk.level == "critical"


def test_systemic_risk_rejects_bad_level():
    with pytest.raises(ValidationError):
        SystemicRisk(headline="x", body="y", level="catastrophic", rule_id="r")


def test_map_point_validates():
    point = MapPoint(id="bb", x=1.2, y=6.0, r=24, kind="anchor")
    assert point.kind == "anchor"


def test_top_picks_holds_seven_each():
    plotted = [MapPoint(id=f"s{i}", x=1.0, y=1.0, r=10, kind="fresh") for i in range(7)]
    grid = [GridEntry(id=f"g{i}", tldr="placeholder") for i in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="s0")
    assert len(picks.plotted) == 7
    assert len(picks.grid) == 7


def test_todays_call_default_byline():
    call = TodaysCall(text="x" * 60, generated_at=datetime.now(timezone.utc))
    assert call.byline == "Desk Editor · The Brief"


def test_editorial_qa_result_shippable_flag():
    result = EditorialQAResult(
        status="block",
        issues=[QAIssue(section_id="bb", severity="block", message="empty banker read")],
        shippable=False,
    )
    assert result.shippable is False


def test_bankerread_v5_full_variant():
    br = BankerReadInsight(
        variant="full",
        meaning="m" * 80,
        action="a" * 80,
        trigger="t" * 80,
        focus="f" * 80,
        pull_quote="quotable line",
        generated_at=datetime.now(timezone.utc),
    )
    assert br.sentences is None
    assert br.variant == "full"


def test_bankerread_v4_legacy_variant_still_works():
    br = BankerReadInsight(
        variant="v4_legacy",
        sentences=["s1", "s2", "s3", "s4"],
        generated_at=datetime.now(timezone.utc),
    )
    assert br.sentences == ["s1", "s2", "s3", "s4"]
    assert br.meaning is None


def test_bankerread_stale_micro_variant():
    br = BankerReadInsight(
        variant="stale_micro",
        meaning="single paragraph " * 8,
        pull_quote="stale-day quotable",
        generated_at=datetime.now(timezone.utc),
    )
    assert br.action is None
    assert br.trigger is None
    assert br.focus is None


def test_section_data_v5_optional_fields_default_safe():
    section = SectionData(
        id="bb",
        title="Bangladesh Bank",
        kicker="Policy & rates",
        tldr="Held again.",
        metrics=[],
        news=[],
        freshness="fresh",
    )
    assert section.systemic_risk is None
    assert section.risk_active is False
    assert section.history_values is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema.py::test_systemic_risk_validates -v`
Expected: FAIL — `ImportError: cannot import name 'SystemicRisk' from 'brief.schema'`.

- [ ] **Step 3: Add new types + extend existing types in `brief/schema.py`**

Open `brief/schema.py`. Locate `BankerReadInsight` (currently has `sentences: list[str]`). Replace it with the V5-extended version below. Then locate `SectionData` and extend it with the new optional fields. Add the new types at the bottom of the file before any `__all__` block.

Replace the existing `BankerReadInsight` class with:

```python
class BankerReadInsight(BaseModel):
    """Banker's read insight, multi-variant.

    V5 path: variant in {"full", "stale_micro"} with structured fields.
    V4 path: variant == "v4_legacy" with `sentences: list[str]`.
    Templates branch on `variant`.
    """
    sentences: list[str] | None = None
    meaning: str | None = None
    action: str | None = None
    trigger: str | None = None
    focus: str | None = None
    pull_quote: str | None = None
    generated_at: datetime
    variant: Literal["full", "stale_micro", "v4_legacy"] = "full"
```

Locate `SectionData` and extend with V5 optional fields. The fully extended class:

```python
class SectionData(BaseModel):
    id: str
    title: str
    kicker: str = ""             # NEW (V5 — back-compat default empty)
    tldr: str = ""               # NEW (V5 — back-compat default empty)
    metrics: list[Metric]
    news: list[NewsItem] = []
    freshness: FreshnessKind
    freshness_reason: str | None = None
    bankerread: BankerReadInsight | None = None
    exec_signals: list[ExecSignal] | None = None
    systemic_risk: "SystemicRisk | None" = None  # NEW
    risk_active: bool = False                     # NEW
    history_values: list[float] | None = None     # NEW
```

Add the new types at the end of the file (before any `__all__`):

```python
class SystemicRisk(BaseModel):
    headline: str
    body: str
    level: Literal["warning", "critical"]
    rule_id: str  # which deterministic rule fired (e.g. "banking_npl_above_30")


class MapPoint(BaseModel):
    id: str
    x: float
    y: float
    r: float
    kind: Literal["event", "fresh", "slow", "anchor"]


class GridEntry(BaseModel):
    id: str
    tldr: str  # ≤ 12 words; validator at validator-layer enforces


class TopPicks(BaseModel):
    plotted: list[MapPoint]
    grid: list[GridEntry]
    front_of_book_id: str


class TodaysCall(BaseModel):
    text: str
    byline: str = "Desk Editor · The Brief"
    generated_at: datetime


class QAIssue(BaseModel):
    section_id: str | None = None
    severity: Literal["info", "warn", "block"]
    message: str


class EditorialQAResult(BaseModel):
    status: Literal["pass", "block"]
    issues: list[QAIssue] = []
    shippable: bool
```

- [ ] **Step 4: Run new tests + verify entire suite still green**

Run: `pytest tests/test_schema.py -v && pytest -q 2>&1 | tail -3`
Expected: all 9 new tests pass; full suite total 521 + 9 = 530.

- [ ] **Step 5: Commit**

```bash
git add brief/schema.py tests/test_schema.py
git commit -m "feat(schema): V5 additions — SystemicRisk, TopPicks, TodaysCall, QA result, BankerRead variant"
```

---

## Phase 2 — Max client: extended thinking support (~30 min)

**Files:**
- Modify: `brief/claude/max_client.py`
- Test: `tests/claude/test_max_client.py`

### Task 2: Add extended_thinking_budget kwarg

- [ ] **Step 1: Read current `brief/claude/max_client.py`**

Run: `head -80 brief/claude/max_client.py`
Note: identify how `run_max(...)` builds the subprocess argv. The kwarg `claude_binary` is already supported.

- [ ] **Step 2: Write failing test**

Add to `tests/claude/test_max_client.py`:

```python
from unittest.mock import patch, MagicMock
from brief.claude.max_client import run_max


def test_extended_thinking_budget_passes_thinking_flag():
    fake_completed = MagicMock(returncode=0, stdout='{"result":"{\\"ok\\":true}", "total_cost_usd":0.01, "duration_ms":100, "usage":{"input_tokens":1,"output_tokens":1}}')
    with patch("subprocess.run", return_value=fake_completed) as mock_run:
        run_max(prompt="hi", extended_thinking_budget=12000)
    args = mock_run.call_args.args[0]
    assert "--thinking-budget" in args
    idx = args.index("--thinking-budget")
    assert args[idx + 1] == "12000"


def test_extended_thinking_budget_default_omits_flag():
    fake_completed = MagicMock(returncode=0, stdout='{"result":"{}", "total_cost_usd":0.0, "duration_ms":50, "usage":{"input_tokens":1,"output_tokens":1}}')
    with patch("subprocess.run", return_value=fake_completed) as mock_run:
        run_max(prompt="hi")
    args = mock_run.call_args.args[0]
    assert "--thinking-budget" not in args
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `pytest tests/claude/test_max_client.py::test_extended_thinking_budget_passes_thinking_flag -v`
Expected: FAIL (kwarg not yet supported).

- [ ] **Step 4: Implement in `brief/claude/max_client.py`**

Update the `run_max` signature and argv construction. Locate the `def run_max(...)` signature near the top of the file. Add `extended_thinking_budget` parameter with default `None`:

```python
def run_max(
    *,
    prompt: str,
    model: str = "claude-opus-4-7",
    timeout_s: int = 1800,
    claude_binary: str | None = None,
    extended_thinking_budget: int | None = None,
) -> MaxCallResult:
```

In the section where argv is built (look for `["claude", "-p", ...`), append the thinking-budget flag after the existing flags:

```python
    argv = [
        binary, "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--no-session-persistence",
        "--tools", "",
        "--permission-mode", "bypassPermissions",
    ]
    if extended_thinking_budget is not None:
        argv += ["--thinking-budget", str(extended_thinking_budget)]
```

- [ ] **Step 5: Run tests + full suite**

Run: `pytest tests/claude/test_max_client.py -v && pytest -q 2>&1 | tail -3`
Expected: 2 new tests pass; full suite green.

- [ ] **Step 6: Commit**

```bash
git add brief/claude/max_client.py tests/claude/test_max_client.py
git commit -m "feat(claude): add extended_thinking_budget kwarg to run_max"
```

---

## Phase 3 — V5 module skeleton + design tokens (~45 min)

**Files:**
- Create: `brief/render/v5/__init__.py`
- Create: `brief/render/v5/_tokens.py`
- Create: `brief/render/v5/tokens.css`
- Create: `brief/render/v5/_jsx.py`
- Test: `tests/render/v5/__init__.py`
- Test: `tests/render/v5/test_tokens.py`
- Test: `tests/render/v5/test_jsx.py`

### Task 3: Create V5 package skeleton

- [ ] **Step 1: Create dirs + empty `__init__.py` files**

```bash
mkdir -p brief/render/v5/chrome brief/render/v5/templates tests/render/v5
touch brief/render/v5/__init__.py brief/render/v5/chrome/__init__.py brief/render/v5/templates/__init__.py tests/render/v5/__init__.py
```

- [ ] **Step 2: Write `brief/render/v5/_tokens.py`**

```python
"""V5 design tokens — Python source of truth.

Mirrors `brief/render/v5/tokens.css` (CSS :root variables). Helpers in
_jsx.py reference these constants directly; templates emit the CSS file
into the page <head>.
"""
from __future__ import annotations

COLORS = {
    "ox":         "#6b1f27",
    "ox_dim":     "#8b3540",
    "ink_1":      "#171310",
    "ink_2":      "#3a322d",
    "ink_3":      "#777",
    "ink_4":      "#aaa",
    "paper_1":    "#faf6ee",
    "paper_2":    "#f1ead9",
    "paper_3":    "#e8e1cd",
    "gold":       "#c89a3f",
    "red":        "#a83a3a",
    "green":      "#3a8f4f",
    "ink_inverse":"#f5f0e8",
}

TYPE = {
    "serif_display": "'Source Serif 4', Georgia, serif",
    "serif_text":    "'Source Serif 4', Georgia, serif",
    "mono":          "'JetBrains Mono', Menlo, monospace",
    "sans":          "'Inter', system-ui, sans-serif",
}

SPACE = {
    "xs": "0.25rem",
    "sm": "0.5rem",
    "md": "1rem",
    "lg": "1.5rem",
    "xl": "2.5rem",
    "2xl": "4rem",
}

KIND_COLOR = {
    "event":  COLORS["ox"],
    "fresh":  COLORS["green"],
    "slow":   COLORS["gold"],
    "anchor": COLORS["ink_1"],
}
```

- [ ] **Step 3: Write `brief/render/v5/tokens.css`**

```css
/* V5 design tokens — must mirror brief/render/v5/_tokens.py. */
:root {
  --ox: #6b1f27;
  --ox-dim: #8b3540;
  --ink-1: #171310;
  --ink-2: #3a322d;
  --ink-3: #777;
  --ink-4: #aaa;
  --paper-1: #faf6ee;
  --paper-2: #f1ead9;
  --paper-3: #e8e1cd;
  --gold: #c89a3f;
  --red: #a83a3a;
  --green: #3a8f4f;
  --ink-inverse: #f5f0e8;

  --font-serif-display: 'Source Serif 4', Georgia, serif;
  --font-serif-text:    'Source Serif 4', Georgia, serif;
  --font-mono:          'JetBrains Mono', Menlo, monospace;
  --font-sans:          'Inter', system-ui, sans-serif;

  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2.5rem;
  --space-2xl: 4rem;
}
```

- [ ] **Step 4: Write tokens parity test**

Create `tests/render/v5/test_tokens.py`:

```python
"""Tokens parity test — every CSS var must have a matching Python token."""
import re
from pathlib import Path

from brief.render.v5 import _tokens

TOKENS_CSS = Path(__file__).parents[3] / "brief" / "render" / "v5" / "tokens.css"


def test_css_var_matches_python_color():
    css = TOKENS_CSS.read_text()
    for key, hex_value in _tokens.COLORS.items():
        # CSS uses hyphens (--ink-1) where Python uses underscores (ink_1)
        css_key = "--" + key.replace("_", "-")
        m = re.search(rf"{re.escape(css_key)}:\s*([^;]+);", css)
        assert m, f"CSS missing var {css_key}"
        assert m.group(1).strip().lower() == hex_value.lower(), \
            f"value mismatch for {key}: py={hex_value} css={m.group(1).strip()}"


def test_css_var_matches_python_type_family():
    css = TOKENS_CSS.read_text()
    py_to_css = {
        "serif_display": "--font-serif-display",
        "serif_text":    "--font-serif-text",
        "mono":          "--font-mono",
        "sans":          "--font-sans",
    }
    for py_key, css_key in py_to_css.items():
        m = re.search(rf"{re.escape(css_key)}:\s*([^;]+);", css)
        assert m, f"CSS missing var {css_key}"
        assert m.group(1).strip() == _tokens.TYPE[py_key], \
            f"value mismatch for {py_key}"
```

- [ ] **Step 5: Run tokens test**

Run: `pytest tests/render/v5/test_tokens.py -v`
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add brief/render/v5/__init__.py brief/render/v5/_tokens.py brief/render/v5/tokens.css brief/render/v5/chrome/__init__.py brief/render/v5/templates/__init__.py tests/render/v5/__init__.py tests/render/v5/test_tokens.py
git commit -m "feat(render/v5): package skeleton + design tokens (Python + CSS)"
```

---

## Phase 4 — V5 JSX helpers (~1 hour)

**Files:**
- Create: `brief/render/v5/_jsx.py`
- Test: `tests/render/v5/test_jsx.py`

### Task 4: V5 helper functions

V5 reuses some V4 helpers (`fmt_num`, `attr`, `_esc`, `sparkline_svg`) but adds new ones for V5-specific elements: `kind_dot`, `freshness_pill`, `cadence_pill_v5`, `pull_quote_card`, `metric_hero_card`, `news_bullet`, `bankerread_panel_v5`, `systemic_risk_callout`.

- [ ] **Step 1: Write the test file with all helper tests**

Create `tests/render/v5/test_jsx.py`:

```python
import re
from datetime import date

import pytest

from brief.render.v5 import _jsx
from brief.schema import (
    BankerReadInsight,
    Metric,
    NewsItem,
    SystemicRisk,
)
from datetime import datetime, timezone


def test_kind_dot_emits_class():
    html = _jsx.kind_dot("event")
    assert 'class="dot dot-event"' in html


def test_kind_dot_rejects_unknown():
    with pytest.raises(ValueError):
        _jsx.kind_dot("explosion")


def test_freshness_pill_fresh_no_visible_text():
    html = _jsx.freshness_pill("fresh")
    assert "FRESH" not in html  # fresh is implied; no pill text


def test_freshness_pill_stale_visible_text():
    html = _jsx.freshness_pill("stale")
    assert "STALE" in html
    assert 'class="freshness-pill freshness-stale"' in html


def test_cadence_pill_uppercases():
    html = _jsx.cadence_pill_v5("daily")
    assert ">DAILY<" in html


def test_pull_quote_card_renders_text():
    html = _jsx.pull_quote_card("Risk premium, not scarcity.")
    assert "Risk premium, not scarcity." in html
    assert 'class="pull-quote-card"' in html


def test_metric_hero_card_with_status_badge():
    metric = Metric(
        id="bb_npl",
        label="NPL Ratio",
        value=35.73,
        unit="%",
        as_of=date(2026, 4, 19),
        source="BB",
        cadence="quarterly",
    )
    html = _jsx.metric_hero_card(metric, badge="HISTORIC HIGH", supporting="World's highest")
    assert "35.73" in html
    assert "HISTORIC HIGH" in html
    assert "World's highest" in html


def test_news_bullet_renders_source_and_date():
    item = NewsItem(
        title="NPL ratio at 35.73%",
        url="https://example.com/x",
        source="TBS",
        published=datetime(2026, 4, 19, tzinfo=timezone.utc),
    )
    html = _jsx.news_bullet(item, summary="The NPL ratio surged to 35.73% as of September 2025...")
    assert "NPL ratio at 35.73%" in html
    assert "TBS" in html
    assert "19 Apr 2026" in html  # date format


def test_bankerread_panel_v5_full_renders_all_four():
    br = BankerReadInsight(
        variant="full",
        meaning="m" * 80,
        action="a" * 80,
        trigger="t" * 80,
        focus="f" * 80,
        pull_quote="quotable",
        generated_at=datetime.now(timezone.utc),
    )
    html = _jsx.bankerread_panel_v5(br, anchor="bb")
    assert "§A" in html
    assert "§B" in html
    assert "§C" in html
    assert "§D" in html


def test_bankerread_panel_v5_stale_renders_meaning_only():
    br = BankerReadInsight(
        variant="stale_micro",
        meaning="single paragraph " * 8,
        pull_quote="quotable",
        generated_at=datetime.now(timezone.utc),
    )
    html = _jsx.bankerread_panel_v5(br, anchor="bb")
    assert "§A" in html
    assert "§B" not in html  # action skipped on stale
    assert "§C" not in html
    assert "§D" not in html


def test_systemic_risk_callout_renders_warning_class():
    risk = SystemicRisk(
        headline="NPL world-high",
        body="Body text " * 10,
        level="warning",
        rule_id="banking_npl_above_30",
    )
    html = _jsx.systemic_risk_callout(risk)
    assert "systemic-risk" in html
    assert "warning" in html
    assert "NPL world-high" in html


def test_no_raw_html_in_news_summary_attack():
    """Defense: news summary must be HTML-escaped to prevent injection."""
    item = NewsItem(
        title="<script>alert(1)</script>",
        url="https://x.test/",
        source="X",
        published=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    html = _jsx.news_bullet(item, summary="<img onerror=x>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img onerror" not in html
    assert "&lt;img" in html
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `pytest tests/render/v5/test_jsx.py -v 2>&1 | head -20`
Expected: ImportError / module-not-found errors for `_jsx` functions.

- [ ] **Step 3: Implement `brief/render/v5/_jsx.py`**

```python
"""V5 JSX helpers — pure functions returning HTML fragment strings.

Reuses V4 helpers (`brief.render.v4._jsx.fmt_num`, `attr`, `_esc`,
`sparkline_svg`) where applicable. New V5 helpers below.
"""
from __future__ import annotations

import html
from typing import Literal

from brief.render.v4._jsx import _esc, _attr_esc, attr, fmt_num, sparkline_svg
from brief.schema import (
    BankerReadInsight,
    Metric,
    NewsItem,
    SystemicRisk,
)

__all__ = [
    "_esc",
    "attr",
    "fmt_num",
    "sparkline_svg",
    "kind_dot",
    "freshness_pill",
    "cadence_pill_v5",
    "pull_quote_card",
    "metric_hero_card",
    "news_bullet",
    "bankerread_panel_v5",
    "systemic_risk_callout",
]

_VALID_KINDS = frozenset({"event", "fresh", "slow", "anchor"})
_VALID_FRESHNESS = frozenset({"fresh", "warming_up", "stale", "warn", "pending", "unavailable"})


def kind_dot(kind: str) -> str:
    """Colored dot for risk-map / legend by kind."""
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind_dot: unknown kind {kind!r}; valid={sorted(_VALID_KINDS)}")
    return f'<span class="dot dot-{kind}"></span>'


def freshness_pill(freshness: str) -> str:
    """Freshness badge. Fresh is implied (no visible pill); others render label."""
    if freshness not in _VALID_FRESHNESS:
        raise ValueError(f"freshness_pill: unknown freshness {freshness!r}")
    if freshness == "fresh":
        return ""  # implied; no visible pill
    label_map = {
        "warming_up": "WARMING UP",
        "stale": "STALE",
        "warn": "WARN",
        "pending": "PENDING",
        "unavailable": "UNAVAILABLE",
    }
    css_state = freshness.replace("_", "-")
    label = label_map[freshness]
    return f'<span class="freshness-pill freshness-{css_state}">{label}</span>'


def cadence_pill_v5(cadence: str) -> str:
    return f'<span class="cadence-pill cadence-{_esc(cadence)}">{_esc(cadence.upper())}</span>'


def pull_quote_card(text: str) -> str:
    """Highlighted single-line editorial quote — used in front-of-book preview."""
    return f'<div class="pull-quote-card"><em>{_esc(text)}</em></div>'


def metric_hero_card(metric: Metric, *, badge: str | None = None, supporting: str | None = None) -> str:
    """Big-display metric card with status badge and supporting text."""
    badge_html = ""
    if badge:
        badge_html = f'<span class="metric-badge">{_esc(badge)}</span>'
    supporting_html = ""
    if supporting:
        supporting_html = f'<p class="metric-supporting">{_esc(supporting)}</p>'
    value_html = fmt_num(metric.value, unit=metric.unit, tabular=True) if isinstance(metric.value, (int, float)) else _esc(str(metric.value))
    return (
        '<div class="metric-card metric-card-hero">'
        f'<div class="metric-label">{_esc(metric.label)}</div>'
        f'<div class="metric-value">{value_html}</div>'
        f'{badge_html}'
        f'{supporting_html}'
        '</div>'
    )


def news_bullet(item: NewsItem, *, summary: str = "") -> str:
    """News bullet with title, summary lede, source/date attribution."""
    pub_label = item.published.strftime("%-d %b %Y")
    return (
        '<li class="news-bullet">'
        f'<a class="news-title" href="{_attr_esc(item.url)}">{_esc(item.title)}</a>'
        f'<p class="news-summary">{_esc(summary)}</p>'
        '<div class="news-attr">'
        f'<span class="news-source">{_esc(item.source)}</span>'
        f' <span class="news-date">{_esc(pub_label)}</span>'
        '</div>'
        '</li>'
    )


def bankerread_panel_v5(br: BankerReadInsight, *, anchor: str) -> str:
    """V5 banker's read panel — dark bg, gold §A/§B/§C/§D labels.

    variant=full: render all four sections.
    variant=stale_micro: render only §A meaning + pull_quote.
    variant=v4_legacy: not supported here — caller must use V4 panel.
    """
    if br.variant == "v4_legacy":
        raise ValueError("bankerread_panel_v5 received v4_legacy variant; use V4 renderer")

    sections_html = ""

    def _block(label: str, body: str | None) -> str:
        if not body:
            return ""
        return (
            '<div class="br-section">'
            f'<span class="br-label">{label}</span>'
            f'<p class="br-content">{_esc(body)}</p>'
            '</div>'
        )

    sections_html += _block("§A MEANING", br.meaning)
    if br.variant == "full":
        sections_html += _block("§B ACTION", br.action)
        sections_html += _block("§C TRIGGER", br.trigger)
        sections_html += _block("§D FOCUS", br.focus)

    pull_html = ""
    if br.pull_quote:
        pull_html = f'<div class="br-pull-quote"><em>{_esc(br.pull_quote)}</em></div>'

    jump_link = (
        f'<a class="bankerread-jump" href="#{_attr_esc(anchor)}">'
        f'← back to map</a>'
    )

    return (
        f'<aside class="bankerread bankerread-v5 br-{br.variant}" id="br-{_attr_esc(anchor)}">'
        f'{pull_html}'
        f'{sections_html}'
        f'{jump_link}'
        '</aside>'
    )


def systemic_risk_callout(risk: SystemicRisk) -> str:
    """Red/amber bordered callout — only rendered when builder fires the rule."""
    return (
        f'<aside class="systemic-risk systemic-risk-{risk.level}" data-rule="{_attr_esc(risk.rule_id)}">'
        f'<div class="systemic-risk-icon" aria-hidden="true">⚠</div>'
        f'<h3 class="systemic-risk-headline">{_esc(risk.headline)}</h3>'
        f'<p class="systemic-risk-body">{_esc(risk.body)}</p>'
        '</aside>'
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/render/v5/test_jsx.py -v`
Expected: all 11 tests pass.

- [ ] **Step 5: Run full suite**

Run: `pytest -q 2>&1 | tail -3`
Expected: 521 + 9 (schema) + 2 (max_client) + 2 (tokens) + 11 (jsx) = 545 passed.

- [ ] **Step 6: Commit**

```bash
git add brief/render/v5/_jsx.py tests/render/v5/test_jsx.py
git commit -m "feat(render/v5): JSX helpers — kind_dot, freshness_pill, hero card, news bullet, bankerread panel, systemic-risk callout"
```

---

## Plan continues — see `2026-04-25-the-brief-v5-pilot-part2.md` for Phases 5-12.

The plan is split because of length. Part 2 covers chrome (live banner, masthead, today's call, risk map, secondary grid, colophon), the 6 editorial Claude calls (prompts, validators, pipeline integration), the pilot `bb` section template, the `BRIEF_RENDERER` env-flag dispatch, mixed-mode rendering, and the local + VPS smoke validation tasks.
