# V5 Plan B — Wave 1: FX, Macro, Remit, NBR templates (PR #21)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four new V5 section templates — FX, Macro, Remittance, NBR — following the bb scaffold from Plan A. Each gets a focused unit-test file with five tests. After this PR merges, four `<section-v4-stub>` placeholders in the V5 daily render are replaced with real editorial sections.

**Architecture:** Pure additive change. Four new template modules under `brief/render/v5/templates/`, four new test files under `tests/render/v5/`, one inline dict in `brief/pipeline.py` extended from 1 entry to 5. No edits to `_section_base.py`, `_jsx.py`, or any V4 builder. The shared scaffold already supports the strict-uniformity contract (§5 of the spec). Each template is a single function, ~30-50 lines, that maps a `SectionData` to HTML by populating `summary_pills`, `metric_cards_html`, and `news_block_html` in `render_section_base()`.

**Tech Stack:** Python 3.14, pytest. No new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-04-29-the-brief-v5-plan-b-design.md](../specs/2026-04-29-the-brief-v5-plan-b-design.md) §3 (Wave 1 row), §4 (file layout), §5 (template contract), §6 (per-section parameters — see corrections below), §7 (testing strategy).

**Branch:** `feat/v5-pilot` (cut a new `feat/v5-wave1` from `feat/v4-retarget` after pulling latest with PR #19 + PR #20 merged).

**Estimated session length:** ~2-3 hours with subagents (4 parallel template tasks + integration + smoke).

---

## Spec deviations grounded in code reality

> Read this section before any task. The spec §6 metric IDs were illustrative ("the implementation plan must verify each ID exists in the schema before use"). Audited 2026-04-29 against the actual V4 builders in `brief/builders/`. Use the values in this plan, not the spec table.

### Section numbers

The spec §6 table says `fx=03, macro=04, remit=05, nbr=06`. The runtime source-of-truth is `brief/pipeline_v5.py::_section_n` which says: **`macro=03, fx=04, remit=05, nbr=12`**. Use the runtime values.

| Section | Section_N | Source |
|---|---|---|
| Macro | `03` | `brief/pipeline_v5.py:355` |
| FX | `04` | `brief/pipeline_v5.py:356` |
| Remit | `05` | `brief/pipeline_v5.py:356` |
| NBR | `12` | `brief/pipeline_v5.py:358` |

### Metric IDs

| Section | Spec §6 IDs | Real V4 builder IDs (use these) |
|---|---|---|
| FX | `fx_usd_bdt`, NEER, REER, gross_reserves | `fx_usd_bdt_mid`, `fx_usd_bdt_buy`, `fx_usd_bdt_sell`, `fx_eur_bdt`, `fx_gbp_bdt` |
| Macro | `cpi_general`, `core_cpi`, `food_cpi`, `fuel_cpi` | `macro_cpi_headline`, `macro_cpi_food`, `macro_gdp_growth`, `macro_credit_growth` |
| Remit | `remit_monthly_inflow`, wires, MTOs, yoy_pct | `remit_monthly_mn`, `remit_yoy_pct` (only two — fewer than the spec's 1 hero + 3 supporting) |
| NBR | `nbr_monthly_collection`, yoy_pct, fytd_pct, vs_target | `nbr_vat_bn`, `nbr_it_bn`, `nbr_customs_bn` (only three — composition, no rolled-up monthly total) |

### Hero / supporting / pills (per real metric availability)

| Section | Hero | Supporting (up to 3) | Pills | Sparkline | Threshold badge |
|---|---|---|---|---|---|
| **fx** | `fx_usd_bdt_mid` | `fx_usd_bdt_buy`, `fx_usd_bdt_sell`, `fx_eur_bdt` | USD/BDT, EUR/BDT, GBP/BDT | yes | `fx_usd_bdt_mid > 124` → WATCH (matches existing rule `fx_usd_bdt_above_124`) |
| **macro** | `macro_cpi_headline` | `macro_cpi_food`, `macro_gdp_growth`, `macro_credit_growth` | CPI, FOOD, GDP | yes | `macro_cpi_headline > 10` → CRITICAL |
| **remit** | `remit_monthly_mn` | `remit_yoy_pct` (only one supporting card) | MONTHLY, YoY% | yes | `remit_yoy_pct < -5` → WATCH |
| **nbr** | `nbr_vat_bn` (largest of the 3) | `nbr_it_bn`, `nbr_customs_bn` | VAT, IT, CUSTOMS | yes | none — current builder has no FYTD/target metric to threshold against |

### Why these deviations are safe

- The spec's "graceful fallback" decision (§2 item 1) was specifically: "Sections without hero metrics … render with empty `metric_cards_html` and let the news block carry the weight." Same principle applies when *fewer* supporting metrics exist — Remit gets one supporting card, NBR gets two. Empty trailing slots simply don't render.
- The risk-rule wiring (`fx_usd_bdt_above_124`, `banking_npl_above_30`) lives in `brief/cadence/` and is fed via the V5 systemic-risk Call 5. The threshold badge in the *template* is independent UX shorthand — it does not need to match every rule for full coverage.
- NBR's "no threshold badge" is honest: the schema doesn't expose a target-vs-actual ratio. Adding one would be a builder change, out of Wave 1 scope.

### Mock-patchable names discipline (carried from Pre-Wave)

This wave doesn't add new code paths through `pipeline_v5.py`, so the late-binding rule (`_pipeline.X(...)` for any test-mocked name) is not directly relevant here. But: the pattern that the new templates follow — pure functions taking `SectionData`, returning `str`, no I/O — is intentionally easy to test without mocks at all. None of the Wave 1 tests should patch anything.

---

## Pre-flight check

Before any task, confirm baseline state.

- [ ] **Step 1: Confirm working tree clean and on the right branch.**

```bash
cd ~/Projects/clauding-lab/the-brief
git fetch origin
git checkout feat/v4-retarget
git pull origin feat/v4-retarget
```

Expected: branch updated. The two most recent merge commits should be PR #20 (`75f624c`-ish) and PR #19 (`f6c082c`-ish).

```bash
git log --oneline -5
```

Expected output includes:
```
... Merge pull request #20 from clauding-lab/feat/v5-prewave
... Merge pull request #19 from clauding-lab/feat/v5-pilot
```

- [ ] **Step 2: Cut the Wave 1 branch.**

```bash
git checkout -b feat/v5-wave1
```

Expected: `Switched to a new branch 'feat/v5-wave1'`.

- [ ] **Step 3: Verify baseline test count.**

```bash
source .venv/bin/activate
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected:
```
612 passed in <N>s
```

`<N>` should be 15-25 seconds. If `<N>` is much larger (>60s), suspect mock-bypass — STOP and investigate before continuing.

If the count is anything other than 612 passed, STOP and report — the baseline drifted.

- [ ] **Step 4: Verify the Pre-Wave split is intact.**

```bash
wc -l brief/pipeline.py brief/pipeline_v5.py
```

Expected: `730 brief/pipeline.py`, `585 brief/pipeline_v5.py` (both under the 800-line cap).

```bash
ls brief/render/v5/templates/
```

Expected:
```
__init__.py    _section_base.py    section_bb.py
```

If `_section_base.py` or `section_bb.py` is missing, the merge state is wrong — STOP.

- [ ] **Step 5: Read the bb reference template and tests.**

Read for shape (do not modify):
- `brief/render/v5/templates/section_bb.py` — 58 lines, the canonical scaffold to copy.
- `tests/render/v5/test_section_bb.py` — 82 lines, the existing test pattern.

The bb tests are the precedent for how to construct fixture `SectionData`. The Wave 1 test files reuse this construction style with section-specific metric IDs.

---

## Task 1: FX section (`§04`)

**Files:**
- Create: `brief/render/v5/templates/section_fx.py`
- Create: `tests/render/v5/test_section_fx.py`

**Goal:** Render the FX section in V5 shape using the five real metric IDs from `brief/builders/fx.py`. Hero = `fx_usd_bdt_mid`. Threshold badge: `fx_usd_bdt_mid > 124` → WATCH.

- [ ] **Step 1: Write the test file (5 tests, fail-first).**

Create `tests/render/v5/test_section_fx.py`:

```python
from datetime import date

import pytest

from brief.render.v5.templates.section_fx import render_section_fx
from brief.schema import Metric, NewsItem, SectionData


def _fx_section(*, with_metrics: bool = True, with_news: bool = True, hero_value: float = 122.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="fx_usd_bdt_mid",  label="USD/BDT mid",  value=hero_value, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_usd_bdt_buy",  label="USD/BDT buy",  value=hero_value - 0.5, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_usd_bdt_sell", label="USD/BDT sell", value=hero_value + 0.5, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_eur_bdt",      label="EUR/BDT",      value=132.10, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
            Metric(id="fx_gbp_bdt",      label="GBP/BDT",      value=154.75, unit="BDT",
                   as_of=date(2026, 4, 28), source="BB", cadence="daily"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Taka steady against dollar mid-week", url="https://example.com/fx1",
                     source="Daily Star", published=date(2026, 4, 28)),
        ]
    return SectionData(
        id="fx", title="Foreign Exchange",
        kicker="FX & RESERVES", tldr="USD/BDT 122.50; eur 132.10",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[121.8, 122.0, 122.1, 122.2, 122.3, 122.4, 122.5],
    )


def test_section_fx_renders_with_full_metrics():
    html = render_section_fx(_fx_section())
    assert 'id="section-fx"' in html
    assert "§04" in html
    assert "FX" in html  # kicker
    assert "Foreign Exchange" in html
    assert "122.50" in html  # hero value
    assert "USD/BDT" in html
    assert "EUR/BDT" in html


def test_section_fx_renders_with_no_metrics():
    section = _fx_section(with_metrics=False)
    html = render_section_fx(section)
    assert 'id="section-fx"' in html
    # No orphan empty metric grid wrappers
    assert "metric-card" not in html


def test_section_fx_renders_with_no_news():
    section = _fx_section(with_news=False)
    html = render_section_fx(section)
    assert 'id="section-fx"' in html
    assert '<ul class="sec-news">' not in html


def test_section_fx_threshold_badge_above_124():
    html = render_section_fx(_fx_section(hero_value=125.5))
    assert "WATCH" in html


def test_section_fx_rejects_wrong_id():
    section = _fx_section().model_copy(update={"id": "macro"})
    with pytest.raises(ValueError):
        render_section_fx(section)
```

- [ ] **Step 2: Run the failing tests.**

```bash
python -m pytest tests/render/v5/test_section_fx.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 tests collected, all fail with `ModuleNotFoundError: No module named 'brief.render.v5.templates.section_fx'`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_fx.py`:

```python
"""V5 §04 — FX & Reserves."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_fx(section: SectionData) -> str:
    if section.id != "fx":
        raise ValueError(f"render_section_fx received id={section.id!r}; expected 'fx'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "fx_usd_bdt_mid" in metrics_by_id:
        m = metrics_by_id["fx_usd_bdt_mid"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">USD/BDT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fx_eur_bdt" in metrics_by_id:
        m = metrics_by_id["fx_eur_bdt"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">EUR/BDT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fx_gbp_bdt" in metrics_by_id:
        m = metrics_by_id["fx_gbp_bdt"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GBP/BDT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "fx_usd_bdt_mid" in metrics_by_id:
        hero = metrics_by_id["fx_usd_bdt_mid"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 124.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="USD/BDT mid spot")

    supporting_cards = []
    for mid in ("fx_usd_bdt_buy", "fx_usd_bdt_sell", "fx_eur_bdt"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="04",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run the tests, expect all pass.**

```bash
python -m pytest tests/render/v5/test_section_fx.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run the full suite, confirm no regressions.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `617 passed in <N>s` where `<N>` is 15-25s. (Old 612 + 5 new FX tests.)

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_fx.py tests/render/v5/test_section_fx.py
git commit -m "feat(v5): add FX section template (§04)

Hero: fx_usd_bdt_mid. Supporting: buy/sell/EUR. Pills: USD/BDT, EUR/BDT,
GBP/BDT. Threshold badge: USD/BDT mid > 124 → WATCH (matches existing
fx_usd_bdt_above_124 systemic-risk rule).

5 unit tests added — full-metrics, no-metrics, no-news, threshold badge,
wrong-id rejection. Tests: 612 → 617."
```

---

## Task 2: Macro section (`§03`)

**Files:**
- Create: `brief/render/v5/templates/section_macro.py`
- Create: `tests/render/v5/test_section_macro.py`

**Goal:** Render the Macro section. Hero = `macro_cpi_headline`. Threshold: `macro_cpi_headline > 10` → CRITICAL.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_macro.py`:

```python
from datetime import date

import pytest

from brief.render.v5.templates.section_macro import render_section_macro
from brief.schema import Metric, NewsItem, SectionData


def _macro_section(*, with_metrics: bool = True, with_news: bool = True, cpi_value: float = 9.4) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="macro_cpi_headline",  label="CPI Headline",  value=cpi_value, unit="%",
                   as_of=date(2026, 3, 31), source="BBS", cadence="monthly"),
            Metric(id="macro_cpi_food",      label="CPI Food",      value=10.8, unit="%",
                   as_of=date(2026, 3, 31), source="BBS", cadence="monthly"),
            Metric(id="macro_gdp_growth",    label="GDP Growth",    value=5.8, unit="%",
                   as_of=date(2026, 3, 31), source="BBS", cadence="quarterly"),
            Metric(id="macro_credit_growth", label="Credit Growth", value=8.5, unit="% YoY",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Headline CPI eases to 9.4%", url="https://example.com/macro1",
                     source="The Daily Star", published=date(2026, 4, 28)),
        ]
    return SectionData(
        id="macro", title="Macro & Inflation",
        kicker="MACRO", tldr=f"CPI Headline: {cpi_value}%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[9.8, 9.7, 9.6, 9.5, 9.5, 9.4, cpi_value],
    )


def test_section_macro_renders_with_full_metrics():
    html = render_section_macro(_macro_section())
    assert 'id="section-macro"' in html
    assert "§03" in html
    assert "MACRO" in html
    assert "Macro &amp; Inflation" in html
    assert "9.40" in html
    assert "CPI" in html


def test_section_macro_renders_with_no_metrics():
    html = render_section_macro(_macro_section(with_metrics=False))
    assert 'id="section-macro"' in html
    assert "metric-card" not in html


def test_section_macro_renders_with_no_news():
    html = render_section_macro(_macro_section(with_news=False))
    assert 'id="section-macro"' in html
    assert '<ul class="sec-news">' not in html


def test_section_macro_threshold_badge_above_10():
    html = render_section_macro(_macro_section(cpi_value=10.5))
    assert "CRITICAL" in html


def test_section_macro_rejects_wrong_id():
    section = _macro_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_macro(section)
```

- [ ] **Step 2: Run the failing tests.**

```bash
python -m pytest tests/render/v5/test_section_macro.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 tests fail with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_macro.py`:

```python
"""V5 §03 — Macro & Inflation."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_macro(section: SectionData) -> str:
    if section.id != "macro":
        raise ValueError(f"render_section_macro received id={section.id!r}; expected 'macro'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "macro_cpi_headline" in metrics_by_id:
        m = metrics_by_id["macro_cpi_headline"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">CPI</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "macro_cpi_food" in metrics_by_id:
        m = metrics_by_id["macro_cpi_food"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">FOOD</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "macro_gdp_growth" in metrics_by_id:
        m = metrics_by_id["macro_gdp_growth"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GDP</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "macro_cpi_headline" in metrics_by_id:
        hero = metrics_by_id["macro_cpi_headline"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 10.0:
            badge = "CRITICAL"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BBS monthly release")

    supporting_cards = []
    for mid in ("macro_cpi_food", "macro_gdp_growth", "macro_credit_growth"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="03",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests, expect all pass.**

```bash
python -m pytest tests/render/v5/test_section_macro.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `622 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_macro.py tests/render/v5/test_section_macro.py
git commit -m "feat(v5): add Macro section template (§03)

Hero: macro_cpi_headline. Supporting: cpi_food/gdp_growth/credit_growth.
Pills: CPI, FOOD, GDP. Threshold: CPI > 10% → CRITICAL.

5 unit tests. Tests: 617 → 622."
```

---

## Task 3: Remit section (`§05`)

**Files:**
- Create: `brief/render/v5/templates/section_remit.py`
- Create: `tests/render/v5/test_section_remit.py`

**Goal:** Render Remittance. Only two metrics exist (`remit_monthly_mn`, `remit_yoy_pct`). Hero = `remit_monthly_mn`. Single supporting card. Threshold: `remit_yoy_pct < -5` → WATCH.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_remit.py`:

```python
from datetime import date

import pytest

from brief.render.v5.templates.section_remit import render_section_remit
from brief.schema import Metric, NewsItem, SectionData


def _remit_section(*, with_metrics: bool = True, with_news: bool = True, yoy: float = 8.4) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="remit_monthly_mn", label="Monthly Remittance", value=2347.0, unit="mn USD",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
            Metric(id="remit_yoy_pct",    label="YoY %",              value=yoy, unit="%",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="March remittances cross $2.3bn", url="https://example.com/remit1",
                     source="Prothom Alo", published=date(2026, 4, 1)),
        ]
    return SectionData(
        id="remit", title="Remittance",
        kicker="REMITTANCES", tldr="Monthly: $2,347mn",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[2100, 2150, 2210, 2280, 2300, 2330, 2347],
    )


def test_section_remit_renders_with_full_metrics():
    html = render_section_remit(_remit_section())
    assert 'id="section-remit"' in html
    assert "§05" in html
    assert "REMITTANCES" in html
    assert "Remittance" in html
    assert "2347" in html or "2,347" in html
    assert "MONTHLY" in html


def test_section_remit_renders_with_no_metrics():
    html = render_section_remit(_remit_section(with_metrics=False))
    assert 'id="section-remit"' in html
    assert "metric-card" not in html


def test_section_remit_renders_with_no_news():
    html = render_section_remit(_remit_section(with_news=False))
    assert 'id="section-remit"' in html
    assert '<ul class="sec-news">' not in html


def test_section_remit_threshold_badge_yoy_below_minus_5():
    html = render_section_remit(_remit_section(yoy=-7.2))
    assert "WATCH" in html


def test_section_remit_rejects_wrong_id():
    section = _remit_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_remit(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_remit.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_remit.py`:

```python
"""V5 §05 — Remittances."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_remit(section: SectionData) -> str:
    if section.id != "remit":
        raise ValueError(f"render_section_remit received id={section.id!r}; expected 'remit'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "remit_monthly_mn" in metrics_by_id:
        m = metrics_by_id["remit_monthly_mn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">MONTHLY</span> <strong>${fmt_num(m.value)}MN</strong></span>')
    if "remit_yoy_pct" in metrics_by_id:
        m = metrics_by_id["remit_yoy_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">YoY%</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "remit_monthly_mn" in metrics_by_id:
        hero = metrics_by_id["remit_monthly_mn"]
        badge = None
        yoy_metric = metrics_by_id.get("remit_yoy_pct")
        if yoy_metric is not None and isinstance(yoy_metric.value, (int, float)) and yoy_metric.value < -5.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BB monthly release")

    supporting_cards = []
    if "remit_yoy_pct" in metrics_by_id:
        supporting_cards.append(metric_hero_card(metrics_by_id["remit_yoy_pct"]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="05",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_remit.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `627 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_remit.py tests/render/v5/test_section_remit.py
git commit -m "feat(v5): add Remit section template (§05)

Hero: remit_monthly_mn. One supporting card (yoy_pct — only 2 metrics in
builder). Pills: MONTHLY, YoY%. Threshold: yoy < -5% → WATCH (badge applied
to hero card based on yoy_pct value).

5 unit tests. Tests: 622 → 627."
```

---

## Task 4: NBR section (`§12`)

**Files:**
- Create: `brief/render/v5/templates/section_nbr.py`
- Create: `tests/render/v5/test_section_nbr.py`

**Goal:** Render NBR Revenue. Three metrics — VAT, IT, Customs. Hero = `nbr_vat_bn`. No threshold badge (no FYTD/target metric available).

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_nbr.py`:

```python
from datetime import date

import pytest

from brief.render.v5.templates.section_nbr import render_section_nbr
from brief.schema import Metric, NewsItem, SectionData


def _nbr_section(*, with_metrics: bool = True, with_news: bool = True, vat_value: float = 142.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="nbr_vat_bn",     label="VAT",        value=vat_value, unit="BDT bn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="nbr_it_bn",      label="Income Tax", value=98.7, unit="BDT bn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="nbr_customs_bn", label="Customs",    value=64.2, unit="BDT bn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="VAT collection up 8% YoY", url="https://example.com/nbr1",
                     source="Bonik Barta", published=date(2026, 4, 5)),
        ]
    return SectionData(
        id="nbr", title="NBR Revenue",
        kicker="TAX & CUSTOMS", tldr=f"VAT: BDT {vat_value}bn",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[120, 125, 130, 135, 138, 140, vat_value],
    )


def test_section_nbr_renders_with_full_metrics():
    html = render_section_nbr(_nbr_section())
    assert 'id="section-nbr"' in html
    assert "§12" in html
    assert "TAX" in html
    assert "NBR Revenue" in html
    assert "142.50" in html
    assert "VAT" in html


def test_section_nbr_renders_with_no_metrics():
    html = render_section_nbr(_nbr_section(with_metrics=False))
    assert 'id="section-nbr"' in html
    assert "metric-card" not in html


def test_section_nbr_renders_with_no_news():
    html = render_section_nbr(_nbr_section(with_news=False))
    assert 'id="section-nbr"' in html
    assert '<ul class="sec-news">' not in html


def test_section_nbr_no_threshold_badge_in_render():
    """NBR has no FYTD/target metric; badge must never appear regardless of values."""
    html_low  = render_section_nbr(_nbr_section(vat_value=10.0))
    html_high = render_section_nbr(_nbr_section(vat_value=999.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_nbr_rejects_wrong_id():
    section = _nbr_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_nbr(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_nbr.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_nbr.py`:

```python
"""V5 §12 — Tax & Customs (NBR)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_nbr(section: SectionData) -> str:
    if section.id != "nbr":
        raise ValueError(f"render_section_nbr received id={section.id!r}; expected 'nbr'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "nbr_vat_bn" in metrics_by_id:
        m = metrics_by_id["nbr_vat_bn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">VAT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "nbr_it_bn" in metrics_by_id:
        m = metrics_by_id["nbr_it_bn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">IT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "nbr_customs_bn" in metrics_by_id:
        m = metrics_by_id["nbr_customs_bn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">CUSTOMS</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "nbr_vat_bn" in metrics_by_id:
        hero = metrics_by_id["nbr_vat_bn"]
        # No threshold badge — current builder has no FYTD/target metric to threshold against.
        hero_html = metric_hero_card(hero, badge=None, supporting="NBR monthly composition")

    supporting_cards = []
    for mid in ("nbr_it_bn", "nbr_customs_bn"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="12",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_nbr.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `632 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_nbr.py tests/render/v5/test_section_nbr.py
git commit -m "feat(v5): add NBR section template (§12)

Hero: nbr_vat_bn (largest of 3 metrics). Supporting: nbr_it_bn,
nbr_customs_bn. Pills: VAT, IT, CUSTOMS. No threshold badge — current
builder has no FYTD/target metric. NBR threshold deferred to a future
schema enhancement.

5 unit tests including a 'badge never appears' guard. Tests: 627 → 632."
```

---

## Task 5: Wire Wave 1 templates into the V5 dispatcher

**Files:**
- Modify: `brief/pipeline.py:646-662` (the V5 mode block in `render_index_html`)

**Goal:** Extend the `section_renderers` dict from `{"bb": render_section_bb}` to include all four Wave 1 templates. Without this, V5 mode still falls back to `<section-v4-stub>` for FX/Macro/Remit/NBR.

- [ ] **Step 1: Read the current dispatch block.**

```bash
sed -n '640,670p' brief/pipeline.py
```

Expected: shows lines including `from brief.render.v5.templates.section_bb import render_section_bb` (line 647) and `section_renderers: dict = {"bb": render_section_bb}` (line 662).

- [ ] **Step 2: Apply the edit.**

In `brief/pipeline.py`, replace the block:

```python
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_bb import render_section_bb
```

with:

```python
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_bb import render_section_bb
        from brief.render.v5.templates.section_fx import render_section_fx
        from brief.render.v5.templates.section_macro import render_section_macro
        from brief.render.v5.templates.section_nbr import render_section_nbr
        from brief.render.v5.templates.section_remit import render_section_remit
```

And replace:

```python
        section_renderers: dict = {"bb": render_section_bb}
```

with:

```python
        section_renderers: dict = {
            "bb": render_section_bb,
            "fx": render_section_fx,
            "macro": render_section_macro,
            "remit": render_section_remit,
            "nbr": render_section_nbr,
        }
```

- [ ] **Step 3: Confirm `pipeline.py` imports resolve.**

```bash
python -c "from brief.pipeline import render_index_html; print('ok')"
```

Expected: `ok`. (Imports are inside the `if mode == 'v5':` block so this won't actually exercise them — but loading `pipeline.py` itself must still succeed.)

- [ ] **Step 4: Confirm a V5-mode dispatch works in process.**

```bash
python -c "
import os
os.environ['BRIEF_RENDERER'] = 'v5'
from brief.render.v5.templates.section_fx import render_section_fx
from brief.render.v5.templates.section_macro import render_section_macro
from brief.render.v5.templates.section_remit import render_section_remit
from brief.render.v5.templates.section_nbr import render_section_nbr
print('all four templates importable:',
      render_section_fx.__module__,
      render_section_macro.__module__,
      render_section_remit.__module__,
      render_section_nbr.__module__)
"
```

Expected:
```
all four templates importable: brief.render.v5.templates.section_fx brief.render.v5.templates.section_macro brief.render.v5.templates.section_remit brief.render.v5.templates.section_nbr
```

- [ ] **Step 5: Run the full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `632 passed in <N>s`. (Same count as Task 4 — the dispatch wiring isn't asserted by any existing test.)

- [ ] **Step 6: Commit.**

```bash
git add brief/pipeline.py
git commit -m "feat(v5): wire FX/Macro/Remit/NBR into V5 dispatcher

Extends the section_renderers dict in pipeline.py from 1 entry (bb only)
to 5. After this commit, V5 mode renders these four sections in their
new editorial shape; the remaining 9 sections continue to fall back to
<section-v4-stub> until Waves 2 and 3 land.

Tests: 632/632 (unchanged — dispatch wiring isn't asserted by unit tests;
smoke render via Task 6 is the human-eyeballed gate)."
```

---

## Task 6: Local smoke render

**Files:** none (read-only verification).

**Goal:** Render a V5 brief locally on Mac, confirm the four new sections render in the new shape (no `section-v4-stub` markers for them), and eyeball the HTML for visual regressions in the four new sections plus bb.

This task involves real Claude calls (~$7-12 per smoke run, see spec §7). **Stop and ask the user before running** — they may want to skip the smoke and rely on the unit-test signal, or run it themselves.

- [ ] **Step 1: Stop and ask.**

Tell the user:
> "Wave 1 templates done locally. 632/632 tests passing. Local smoke render of all 14 sections will fire real Claude calls (~$7-12). Three options: (a) run the smoke now; (b) skip smoke and ship the PR; (c) you run the smoke yourself. Which?"

Wait for explicit choice.

- [ ] **Step 2: If user chose (a), run the smoke.**

```bash
mkdir -p /tmp/wave1-smoke
BRIEF_RENDERER=v5 python -m brief.cli run --artifacts-dir /tmp/wave1-smoke 2>&1 | tail -20
```

Expected: completes in 200-400 seconds, exits 0, deposits `index.html` in `/tmp/wave1-smoke/`.

- [ ] **Step 3: Verify output (Step 2 only).**

```bash
test -f /tmp/wave1-smoke/index.html && echo "render ok"
grep -c "section-v4-stub" /tmp/wave1-smoke/index.html
```

Expected: `render ok`. The grep count should be `9` (headlines, dse, tbond, iranwar, banking, comm, fiscal, dam, exec) — not `13` like before Wave 1 and not `0`. If the count is 13, dispatcher wiring failed; if 0, something rendered the stubs as real sections (also a bug).

- [ ] **Step 4: Verify the four new sections actually rendered.**

```bash
for sid in fx macro remit nbr; do
  count=$(grep -c "id=\"section-${sid}\"" /tmp/wave1-smoke/index.html)
  echo "${sid}: ${count}"
done
```

Expected: each prints `1` (one section element per section).

- [ ] **Step 5: Open in the browser.**

```bash
open /tmp/wave1-smoke/index.html
```

Visually inspect:
- §03 Macro renders with hero CPI card and 3 supporting cards
- §04 FX renders with USD/BDT mid hero and 3 supporting cards
- §05 Remit renders with monthly hero and 1 supporting card (compact is OK)
- §12 NBR renders with VAT hero and 2 supporting cards (no badge)
- bb (§02) still renders correctly (no regression)
- Threshold badges show only when the test fixture would have triggered them

If any section renders with the wrong scaffold or visibly broken layout, STOP and report. The likely fix is template-level — not a refactor.

- [ ] **Step 6: Record outcome (no commit).**

This task is read-only. No git changes.

---

## Task 7: Push and open PR (gated on user approval)

**Goal:** Push `feat/v5-wave1` and open PR #21 against `feat/v4-retarget`.

This task involves shared-state actions (push to origin, GitHub PR creation) that need explicit user approval per the user's standing rule. Do NOT automate.

- [ ] **Step 1: Stop and ask.**

Tell the user:
> "Wave 1 done locally. 632/632 tests passing. Six commits on `feat/v5-wave1`. May I push to origin and open PR #21 against `feat/v4-retarget`?"

Wait for action-explicit approval like "yes, push and open PR #21".

- [ ] **Step 2: Push.**

```bash
git push -u origin feat/v5-wave1
```

Expected: branch created on remote.

- [ ] **Step 3: Open the PR.**

```bash
gh pr create --base feat/v4-retarget --head feat/v5-wave1 --title "feat(v5): Wave 1 — FX, Macro, Remit, NBR section templates" --body "$(cat <<'EOF'
## Summary

V5 Plan B Wave 1 — four new section templates following the bb scaffold:

- **§03 Macro** — hero `macro_cpi_headline`; CPI > 10% → CRITICAL
- **§04 FX** — hero `fx_usd_bdt_mid`; USD/BDT > 124 → WATCH
- **§05 Remit** — hero `remit_monthly_mn`; yoy < -5% → WATCH
- **§12 NBR** — hero `nbr_vat_bn`; no threshold (no FYTD/target metric available)

Each template is a single function that maps `SectionData` to HTML via `render_section_base()`. No edits to `_section_base.py`, `_jsx.py`, or any V4 builder. The `section_renderers` dict in `pipeline.py` grows from 1 entry (bb only) to 5.

After merge, four `<section-v4-stub>` placeholders in V5 daily render are replaced with real editorial sections. Nine stubs remain (Waves 2 + 3).

### Spec deviations from §6 of the design doc

The spec table was illustrative ("verify each ID exists in the schema"). Real metric IDs from the V4 builders:

- FX: `fx_usd_bdt_mid/buy/sell`, `fx_eur_bdt`, `fx_gbp_bdt` (no NEER/REER; reserves live in bb)
- Macro: `macro_cpi_headline`, `macro_cpi_food`, `macro_gdp_growth`, `macro_credit_growth`
- Remit: `remit_monthly_mn`, `remit_yoy_pct` (only 2 metrics — single supporting card)
- NBR: `nbr_vat_bn`, `nbr_it_bn`, `nbr_customs_bn` (composition; no rolled-up monthly total or fytd)

Section numbers from `pipeline_v5._section_n`: macro=03, fx=04, remit=05, nbr=12 (the spec table had different numbers).

### Test plan

- [x] 5 unit tests per section × 4 sections = +20 tests; suite 612 → 632 passing
- [x] Each test file covers: full-metrics, no-metrics, no-news, threshold-badge (or "no badge" guard for NBR), wrong-id ValueError
- [x] All four template modules under 60 lines; bb remains unchanged at 58 lines
- [ ] Manual: local smoke render (Task 6) eyeballed by reviewer

### Out of scope

- Wave 2 (DSE, T-Bonds, Commodities, DAM, Fiscal) — separate PR
- Wave 3 (Headlines, Iran War, Banking, Exec) — separate PR
- Tiered model routing — parked
- Re-enabling `brief.timer` on VPS — separate decision
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 4: Verify PR state.**

```bash
gh pr view --json number,state,mergeable,baseRefName,headRefName,additions,deletions,changedFiles
```

Expected: `state=OPEN`, `mergeable=MERGEABLE`, `baseRefName=feat/v4-retarget`, `headRefName=feat/v5-wave1`, `changedFiles=9` (4 new templates + 4 new test files + 1 modified pipeline.py).

---

## Acceptance criteria for PR #21

When all seven tasks are checked off:

- ✓ Four new files under `brief/render/v5/templates/`: `section_fx.py`, `section_macro.py`, `section_remit.py`, `section_nbr.py` — each ≤60 lines.
- ✓ Four new test files under `tests/render/v5/`: `test_section_fx.py`, `test_section_macro.py`, `test_section_remit.py`, `test_section_nbr.py` — each with 5 tests.
- ✓ `brief/pipeline.py` `section_renderers` dict has 5 entries (bb + 4 new).
- ✓ All 632 tests pass; no regression in the previous 612.
- ✓ Test suite runs in 15-25 seconds (proves no real Claude calls fired).
- ✓ Local smoke (Task 6) eyeballed and approved (or explicitly skipped).
- ✓ PR #21 open against `feat/v4-retarget`, MERGEABLE, CLEAN.

After PR #21 merges, Wave 2 plan-write begins against the further-extended dispatcher.
