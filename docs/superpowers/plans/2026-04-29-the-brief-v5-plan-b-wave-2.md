# V5 Plan B — Wave 2: DSE, T-Bond, Commodities, Fiscal, DAM templates (PR #22)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five new V5 section templates — DSE, T-Bond, Commodities, Fiscal, DAM — following the bb/Wave-1 scaffold. After this PR merges, five additional `<section-v4-stub>` placeholders in V5 daily render are replaced with real editorial sections.

**Architecture:** Pure additive change. Five new template modules under `brief/render/v5/templates/`, five new test files under `tests/render/v5/`, the `section_renderers` dict in `brief/pipeline.py` extended from 5 entries to 10. No edits to `_section_base.py`, `_jsx.py`, or any V4 builder. The shared scaffold already supports the strict-uniformity contract.

**Tech Stack:** Python 3.14, pytest. No new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-04-29-the-brief-v5-plan-b-design.md](../specs/2026-04-29-the-brief-v5-plan-b-design.md) §3 (Wave 2 row), §4, §5, §6 (with corrections below), §7.

**Wave 1 reference:** [docs/superpowers/plans/2026-04-29-the-brief-v5-plan-b-wave-1.md](./2026-04-29-the-brief-v5-plan-b-wave-1.md). Wave 1 (PR #21) merged 2026-04-29 and shipped FX, Macro, Remit, NBR. Wave 2 follows the exact same task shape per section.

**Branch:** `feat/v5-wave2` (already cut from `feat/v4-retarget` after PR #21 merged; baseline 632/632 verified passing).

**Estimated session length:** ~3-4 hours with subagents (5 mechanical TDD template tasks + integration + push).

---

## Spec deviations grounded in code reality

> Read this section before any task. Same audit pattern as Wave 1 — actual V4 builder metric IDs differ from the spec §6 illustrative table. Use the values in this plan, not the spec table.

### Section numbers (from `brief/pipeline_v5.py::_section_n`)

| Section | Section_N | Spec §6 said |
|---|---|---|
| DSE | `06` | `07` (wrong) |
| T-Bond | `07` | `09` (wrong) |
| Commodities | `10` | `10` ✓ |
| Fiscal | `11` | `12` (wrong) |
| DAM | `13` | `11` (wrong) |

### Metric IDs (from `brief/builders/`)

| Section | Real V4 builder IDs |
|---|---|
| dse | `dse_dsex_close`, `dse_dsex_change_pct`, `dse_ds30`, `dse_dses`, `dse_turnover_crore`, `dse_advancing`, `dse_declining` |
| tbond | `tbond_tbill_91d`, `tbond_tbill_182d`, `tbond_tbill_364d`, `tbond_bond_5y`, `tbond_bond_10y` |
| comm | `comm_gold_usd_oz`, `comm_gold_22k_bdt`, `comm_lng_jkm` (no brent — that lives in `iranwar` builder) |
| fiscal | `fiscal_nbr_collected_trn`, `fiscal_nbr_target_trn`, `fiscal_adp_pct`, `fiscal_govt_borrow_trn` |
| dam | `dam_rice_coarse`, `dam_rice_fine`, `dam_lentil`, `dam_oil`, `dam_sugar`, `dam_onion`, `dam_egg`, `dam_chicken`, `dam_flour` |

### Hero / supporting / pills / threshold (per real metric availability)

| Section | Hero | Supporting (3) | Pills | Threshold |
|---|---|---|---|---|
| **dse** | `dse_dsex_close` | `dse_ds30`, `dse_dses`, `dse_turnover_crore` | DSEX, DS30, TURNOVER | breadth_pct < 30 → WATCH (computed inline as `advancing / (advancing + declining) * 100` when both metrics present) |
| **tbond** | `tbond_bond_10y` | `tbond_bond_5y`, `tbond_tbill_364d`, `tbond_tbill_91d` | 10Y, 5Y, 91D | 10y > 12% → WATCH |
| **comm** | `comm_gold_usd_oz` | `comm_gold_22k_bdt`, `comm_lng_jkm` (only 2 supporting cards) | GOLD, GOLD 22K, LNG | none (spec wanted brent threshold; brent not in this builder) |
| **fiscal** | `fiscal_nbr_collected_trn` | `fiscal_nbr_target_trn`, `fiscal_adp_pct`, `fiscal_govt_borrow_trn` | COLLECTED, ADP, BORROW | none (no deficit metric in builder) |
| **dam** | `dam_rice_coarse` | `dam_flour`, `dam_lentil`, `dam_oil` | RICE, FLOUR, LENTIL | none (V4 builder doesn't populate `delta` for history-backed metrics; mom-change check needs builder support) |

### Test pattern

Same as Wave 1: 5 tests per section. For sections without threshold (comm, fiscal, dam), the threshold-test slot is repurposed as "no badge ever appears" guard (per the NBR precedent in Wave 1). Total: 5 × 5 = 25 new tests → 657.

### Mock-patchable names discipline

Same as Wave 1: pure functions, no mocks needed. Tests don't patch anything.

---

## Pre-flight check

Already partially complete (branch `feat/v5-wave2` exists, 632/632 baseline verified). Re-run if any time has passed.

- [ ] **Step 1: Confirm branch state.**

```bash
cd ~/Projects/clauding-lab/the-brief
git status --short --branch
```

Expected: `## feat/v5-wave2...origin/feat/v5-wave2` OR `## feat/v5-wave2` (if not pushed yet — that's fine).

- [ ] **Step 2: Verify baseline test count.**

```bash
source .venv/bin/activate
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `632 passed in <N>s` where `<N>` is 15-40s. If 60+, suspect mock-bypass; STOP.

- [ ] **Step 3: Confirm Wave 1 templates are present (already merged).**

```bash
ls brief/render/v5/templates/
```

Expected:
```
__init__.py    _section_base.py    section_bb.py    section_fx.py    section_macro.py    section_nbr.py    section_remit.py
```

If any of fx/macro/nbr/remit are missing, the merge state is wrong — STOP.

---

## Task 1: DSE section (`§06`)

**Files:**
- Create: `brief/render/v5/templates/section_dse.py`
- Create: `tests/render/v5/test_section_dse.py`

**Goal:** Render DSE markets section. Hero = `dse_dsex_close`. Threshold computed inline: breadth_pct = advancing / (advancing + declining) × 100; < 30 → WATCH.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_dse.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_dse import render_section_dse
from brief.schema import Metric, NewsItem, SectionData


def _dse_section(*, with_metrics: bool = True, with_news: bool = True,
                 advancing: float = 220, declining: float = 110) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="dse_dsex_close",      label="DSEX close",  value=5481.42, unit="index",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_dsex_change_pct", label="DSEX %Δ",     value=0.45, unit="%",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_ds30",            label="DS30",        value=2007.31, unit="index",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_dses",            label="DSES",        value=1196.55, unit="index",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_turnover_crore",  label="Turnover",    value=620.5, unit="crore BDT",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_advancing",       label="Advancing",   value=advancing, unit="stocks",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
            Metric(id="dse_declining",       label="Declining",   value=declining, unit="stocks",
                   as_of=date(2026, 4, 28), source="DSE", cadence="daily"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="DSEX edges up on banking gains", url="https://example.com/dse1",
                     source="The Daily Star", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="dse", title="DSE Markets",
        kicker="EQUITIES", tldr="DSEX 5,481; turnover 620cr",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[5410, 5430, 5450, 5460, 5470, 5475, 5481],
    )


def test_section_dse_renders_with_full_metrics():
    html = render_section_dse(_dse_section())
    assert 'id="section-dse"' in html
    assert "§06" in html
    assert "EQUITIES" in html
    assert "DSE Markets" in html
    assert "5481.42" in html or "5,481.42" in html
    assert "DSEX" in html
    assert "DS30" in html
    assert "TURNOVER" in html


def test_section_dse_renders_with_no_metrics():
    html = render_section_dse(_dse_section(with_metrics=False))
    assert 'id="section-dse"' in html
    assert "metric-card" not in html


def test_section_dse_renders_with_no_news():
    html = render_section_dse(_dse_section(with_news=False))
    assert 'id="section-dse"' in html
    assert '<ul class="sec-news">' not in html


def test_section_dse_threshold_badge_breadth_below_30():
    # advancing=50, declining=200 → breadth = 50/(50+200) = 20% → WATCH
    html = render_section_dse(_dse_section(advancing=50, declining=200))
    assert "WATCH" in html


def test_section_dse_rejects_wrong_id():
    section = _dse_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_dse(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_dse.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_dse.py`:

```python
"""V5 §06 — Equities (DSE)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_dse(section: SectionData) -> str:
    if section.id != "dse":
        raise ValueError(f"render_section_dse received id={section.id!r}; expected 'dse'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "dse_dsex_close" in metrics_by_id:
        m = metrics_by_id["dse_dsex_close"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">DSEX</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dse_ds30" in metrics_by_id:
        m = metrics_by_id["dse_ds30"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">DS30</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dse_turnover_crore" in metrics_by_id:
        m = metrics_by_id["dse_turnover_crore"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">TURNOVER</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "dse_dsex_close" in metrics_by_id:
        hero = metrics_by_id["dse_dsex_close"]
        badge = None
        adv = metrics_by_id.get("dse_advancing")
        dec = metrics_by_id.get("dse_declining")
        if (adv is not None and dec is not None
                and isinstance(adv.value, (int, float))
                and isinstance(dec.value, (int, float))
                and (adv.value + dec.value) > 0):
            breadth_pct = (adv.value / (adv.value + dec.value)) * 100
            if breadth_pct < 30:
                badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="DSE daily close")

    supporting_cards = []
    for mid in ("dse_ds30", "dse_dses", "dse_turnover_crore"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="06",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_dse.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `637 passed in <N>s`. If `<N>` > 60s, mock-bypass — STOP.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_dse.py tests/render/v5/test_section_dse.py
git commit -m "feat(v5): add DSE section template (§06)

Hero: dse_dsex_close. Supporting: ds30/dses/turnover_crore. Pills: DSEX,
DS30, TURNOVER. Threshold computed inline: breadth_pct < 30 → WATCH
(advancing / (advancing + declining) × 100).

5 unit tests. Tests: 632 → 637."
```

---

## Task 2: T-Bond section (`§07`)

**Files:**
- Create: `brief/render/v5/templates/section_tbond.py`
- Create: `tests/render/v5/test_section_tbond.py`

**Goal:** Render T-Bond / T-Bill yields. Hero = `tbond_bond_10y`. Threshold: 10y > 12% → WATCH.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_tbond.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_tbond import render_section_tbond
from brief.schema import Metric, NewsItem, SectionData


def _tbond_section(*, with_metrics: bool = True, with_news: bool = True,
                   bond_10y: float = 11.42) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="tbond_tbill_91d",  label="91d T-Bill cut-off",  value=9.85, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_tbill_182d", label="182d T-Bill cut-off", value=10.20, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_tbill_364d", label="364d T-Bill cut-off", value=10.55, unit="%",
                   as_of=date(2026, 4, 21), source="BB", cadence="event"),
            Metric(id="tbond_bond_5y",    label="5y Govt Bond",        value=11.10, unit="%",
                   as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
            Metric(id="tbond_bond_10y",   label="10y Govt Bond",       value=bond_10y, unit="%",
                   as_of=date(2026, 4, 25), source="BB", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="10y bond yield holds above 11%", url="https://example.com/tbond1",
                     source="The Financial Express", published=datetime(2026, 4, 25, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="tbond", title="T-Bonds & T-Bills",
        kicker="TREASURY", tldr=f"10y: {bond_10y}%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[11.0, 11.1, 11.2, 11.25, 11.3, 11.38, bond_10y],
    )


def test_section_tbond_renders_with_full_metrics():
    html = render_section_tbond(_tbond_section())
    assert 'id="section-tbond"' in html
    assert "§07" in html
    assert "TREASURY" in html
    assert "T-Bonds" in html
    assert "11.42" in html
    assert "10Y" in html
    assert "5Y" in html
    assert "91D" in html


def test_section_tbond_renders_with_no_metrics():
    html = render_section_tbond(_tbond_section(with_metrics=False))
    assert 'id="section-tbond"' in html
    assert "metric-card" not in html


def test_section_tbond_renders_with_no_news():
    html = render_section_tbond(_tbond_section(with_news=False))
    assert 'id="section-tbond"' in html
    assert '<ul class="sec-news">' not in html


def test_section_tbond_threshold_badge_above_12():
    html = render_section_tbond(_tbond_section(bond_10y=12.5))
    assert "WATCH" in html


def test_section_tbond_rejects_wrong_id():
    section = _tbond_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_tbond(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_tbond.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_tbond.py`:

```python
"""V5 §07 — Treasury (T-Bonds & T-Bills)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_tbond(section: SectionData) -> str:
    if section.id != "tbond":
        raise ValueError(f"render_section_tbond received id={section.id!r}; expected 'tbond'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "tbond_bond_10y" in metrics_by_id:
        m = metrics_by_id["tbond_bond_10y"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">10Y</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "tbond_bond_5y" in metrics_by_id:
        m = metrics_by_id["tbond_bond_5y"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">5Y</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "tbond_tbill_91d" in metrics_by_id:
        m = metrics_by_id["tbond_tbill_91d"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">91D</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "tbond_bond_10y" in metrics_by_id:
        hero = metrics_by_id["tbond_bond_10y"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 12.0:
            badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BB weekly auction")

    supporting_cards = []
    for mid in ("tbond_bond_5y", "tbond_tbill_364d", "tbond_tbill_91d"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="07",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_tbond.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `642 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_tbond.py tests/render/v5/test_section_tbond.py
git commit -m "feat(v5): add T-Bond section template (§07)

Hero: tbond_bond_10y. Supporting: bond_5y/tbill_364d/tbill_91d. Pills:
10Y, 5Y, 91D. Threshold: 10y > 12% → WATCH.

5 unit tests. Tests: 637 → 642."
```

---

## Task 3: Commodities section (`§10`)

**Files:**
- Create: `brief/render/v5/templates/section_comm.py`
- Create: `tests/render/v5/test_section_comm.py`

**Goal:** Render Commodities. Hero = `comm_gold_usd_oz`. Two supporting cards (gold_22k, lng_jkm). No threshold badge.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_comm.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_comm import render_section_comm
from brief.schema import Metric, NewsItem, SectionData


def _comm_section(*, with_metrics: bool = True, with_news: bool = True,
                  gold_oz: float = 2415.50) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="comm_gold_usd_oz",  label="Gold",     value=gold_oz, unit="USD/oz",
                   as_of=date(2026, 4, 28), source="EconDelta", cadence="daily"),
            Metric(id="comm_gold_22k_bdt", label="Gold 22K", value=147500.0, unit="BDT/bhori",
                   as_of=date(2026, 4, 28), source="BAJUS", cadence="daily"),
            Metric(id="comm_lng_jkm",      label="LNG JKM",  value=12.4, unit="USD/MMBtu",
                   as_of=date(2026, 4, 25), source="History", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Gold pulls back from $2,420 high", url="https://example.com/comm1",
                     source="Reuters", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="comm", title="Commodities",
        kicker="COMMODITIES", tldr=f"Gold ${gold_oz}/oz",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[2380, 2390, 2400, 2410, 2415, 2420, gold_oz],
    )


def test_section_comm_renders_with_full_metrics():
    html = render_section_comm(_comm_section())
    assert 'id="section-comm"' in html
    assert "§10" in html
    assert "COMMODITIES" in html
    assert "Commodities" in html
    assert "2415.50" in html or "2,415.50" in html
    assert "GOLD" in html
    assert "LNG" in html


def test_section_comm_renders_with_no_metrics():
    html = render_section_comm(_comm_section(with_metrics=False))
    assert 'id="section-comm"' in html
    assert "metric-card" not in html


def test_section_comm_renders_with_no_news():
    html = render_section_comm(_comm_section(with_news=False))
    assert 'id="section-comm"' in html
    assert '<ul class="sec-news">' not in html


def test_section_comm_no_threshold_badge_in_render():
    """comm has no brent metric in this builder; badge must never appear."""
    html_low  = render_section_comm(_comm_section(gold_oz=1500.0))
    html_high = render_section_comm(_comm_section(gold_oz=4500.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_comm_rejects_wrong_id():
    section = _comm_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_comm(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_comm.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_comm.py`:

```python
"""V5 §10 — Commodities."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_comm(section: SectionData) -> str:
    if section.id != "comm":
        raise ValueError(f"render_section_comm received id={section.id!r}; expected 'comm'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "comm_gold_usd_oz" in metrics_by_id:
        m = metrics_by_id["comm_gold_usd_oz"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GOLD</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "comm_gold_22k_bdt" in metrics_by_id:
        m = metrics_by_id["comm_gold_22k_bdt"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">GOLD 22K</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "comm_lng_jkm" in metrics_by_id:
        m = metrics_by_id["comm_lng_jkm"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">LNG</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "comm_gold_usd_oz" in metrics_by_id:
        hero = metrics_by_id["comm_gold_usd_oz"]
        # No threshold badge — spec wanted brent threshold; brent lives in iranwar builder.
        hero_html = metric_hero_card(hero, badge=None, supporting="EconDelta daily spot")

    supporting_cards = []
    for mid in ("comm_gold_22k_bdt", "comm_lng_jkm"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="10",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_comm.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `647 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_comm.py tests/render/v5/test_section_comm.py
git commit -m "feat(v5): add Commodities section template (§10)

Hero: comm_gold_usd_oz. Supporting: gold_22k_bdt, lng_jkm (only 2 — no
brent in this builder; brent lives in iranwar). Pills: GOLD, GOLD 22K,
LNG. No threshold badge.

5 unit tests including 'no badge ever' guard. Tests: 642 → 647."
```

---

## Task 4: Fiscal section (`§11`)

**Files:**
- Create: `brief/render/v5/templates/section_fiscal.py`
- Create: `tests/render/v5/test_section_fiscal.py`

**Goal:** Render Fiscal. Hero = `fiscal_nbr_collected_trn`. No threshold badge.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_fiscal.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_fiscal import render_section_fiscal
from brief.schema import Metric, NewsItem, SectionData


def _fiscal_section(*, with_metrics: bool = True, with_news: bool = True,
                    collected: float = 2.84) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="fiscal_nbr_collected_trn", label="NBR collected YTD", value=collected, unit="BDT trn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="fiscal_nbr_target_trn",    label="NBR full-year target", value=4.78, unit="BDT trn",
                   as_of=date(2026, 3, 31), source="NBR", cadence="monthly"),
            Metric(id="fiscal_adp_pct",           label="ADP utilisation",      value=42.5, unit="%",
                   as_of=date(2026, 3, 31), source="IMED", cadence="monthly"),
            Metric(id="fiscal_govt_borrow_trn",   label="Govt bank borrow YTD", value=0.96, unit="BDT trn",
                   as_of=date(2026, 3, 31), source="BB", cadence="monthly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="ADP utilisation lags target", url="https://example.com/fiscal1",
                     source="The Daily Star", published=datetime(2026, 4, 5, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="fiscal", title="Fiscal",
        kicker="FISCAL", tldr=f"NBR YTD: BDT {collected}trn",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[2.0, 2.2, 2.4, 2.55, 2.65, 2.75, collected],
    )


def test_section_fiscal_renders_with_full_metrics():
    html = render_section_fiscal(_fiscal_section())
    assert 'id="section-fiscal"' in html
    assert "§11" in html
    assert "FISCAL" in html
    assert "Fiscal" in html
    assert "2.84" in html
    assert "COLLECTED" in html
    assert "ADP" in html
    assert "BORROW" in html


def test_section_fiscal_renders_with_no_metrics():
    html = render_section_fiscal(_fiscal_section(with_metrics=False))
    assert 'id="section-fiscal"' in html
    assert "metric-card" not in html


def test_section_fiscal_renders_with_no_news():
    html = render_section_fiscal(_fiscal_section(with_news=False))
    assert 'id="section-fiscal"' in html
    assert '<ul class="sec-news">' not in html


def test_section_fiscal_no_threshold_badge_in_render():
    """fiscal has no deficit/pace metric in this builder; badge must never appear."""
    html_low  = render_section_fiscal(_fiscal_section(collected=0.1))
    html_high = render_section_fiscal(_fiscal_section(collected=99.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_fiscal_rejects_wrong_id():
    section = _fiscal_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_fiscal(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_fiscal.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_fiscal.py`:

```python
"""V5 §11 — Fiscal."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_fiscal(section: SectionData) -> str:
    if section.id != "fiscal":
        raise ValueError(f"render_section_fiscal received id={section.id!r}; expected 'fiscal'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "fiscal_nbr_collected_trn" in metrics_by_id:
        m = metrics_by_id["fiscal_nbr_collected_trn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">COLLECTED</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fiscal_adp_pct" in metrics_by_id:
        m = metrics_by_id["fiscal_adp_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">ADP</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "fiscal_govt_borrow_trn" in metrics_by_id:
        m = metrics_by_id["fiscal_govt_borrow_trn"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">BORROW</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "fiscal_nbr_collected_trn" in metrics_by_id:
        hero = metrics_by_id["fiscal_nbr_collected_trn"]
        # No threshold badge — current builder has no deficit/pace metric.
        hero_html = metric_hero_card(hero, badge=None, supporting="NBR YTD vs annual target")

    supporting_cards = []
    for mid in ("fiscal_nbr_target_trn", "fiscal_adp_pct", "fiscal_govt_borrow_trn"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="11",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_fiscal.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `652 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_fiscal.py tests/render/v5/test_section_fiscal.py
git commit -m "feat(v5): add Fiscal section template (§11)

Hero: fiscal_nbr_collected_trn. Supporting: target_trn, adp_pct,
govt_borrow_trn. Pills: COLLECTED, ADP, BORROW. No threshold badge —
current builder has no deficit/pace metric.

5 unit tests including 'no badge ever' guard. Tests: 647 → 652."
```

---

## Task 5: DAM section (`§13`)

**Files:**
- Create: `brief/render/v5/templates/section_dam.py`
- Create: `tests/render/v5/test_section_dam.py`

**Goal:** Render DAM food prices. Hero = `dam_rice_coarse`. No threshold badge.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_dam.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_dam import render_section_dam
from brief.schema import Metric, NewsItem, SectionData


def _dam_section(*, with_metrics: bool = True, with_news: bool = True,
                 rice: float = 58.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="dam_rice_coarse", label="Rice (coarse)", value=rice, unit="BDT/kg",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
            Metric(id="dam_flour",       label="Wheat flour",   value=52.0, unit="BDT/kg",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
            Metric(id="dam_lentil",      label="Red lentil",    value=125.0, unit="BDT/kg",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
            Metric(id="dam_oil",         label="Soybean oil",   value=178.0, unit="BDT/L",
                   as_of=date(2026, 4, 25), source="DAM Bangladesh", cadence="weekly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Rice prices firm in Dhaka markets", url="https://example.com/dam1",
                     source="The Daily Star", published=datetime(2026, 4, 25, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="dam", title="DAM Food Prices",
        kicker="FOOD PRICES", tldr=f"Rice coarse: BDT {rice}/kg",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[55.0, 56.0, 57.0, 57.5, 58.0, 58.2, rice],
    )


def test_section_dam_renders_with_full_metrics():
    html = render_section_dam(_dam_section())
    assert 'id="section-dam"' in html
    assert "§13" in html
    assert "FOOD" in html
    assert "DAM Food Prices" in html
    assert "58.50" in html
    assert "RICE" in html
    assert "FLOUR" in html
    assert "LENTIL" in html


def test_section_dam_renders_with_no_metrics():
    html = render_section_dam(_dam_section(with_metrics=False))
    assert 'id="section-dam"' in html
    assert "metric-card" not in html


def test_section_dam_renders_with_no_news():
    html = render_section_dam(_dam_section(with_news=False))
    assert 'id="section-dam"' in html
    assert '<ul class="sec-news">' not in html


def test_section_dam_no_threshold_badge_in_render():
    """dam V4 builder doesn't populate Metric.delta; badge must never appear."""
    html_low  = render_section_dam(_dam_section(rice=10.0))
    html_high = render_section_dam(_dam_section(rice=999.0))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_dam_rejects_wrong_id():
    section = _dam_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_dam(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_dam.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_dam.py`:

```python
"""V5 §13 — Food prices (DAM Bangladesh)."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_dam(section: SectionData) -> str:
    if section.id != "dam":
        raise ValueError(f"render_section_dam received id={section.id!r}; expected 'dam'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "dam_rice_coarse" in metrics_by_id:
        m = metrics_by_id["dam_rice_coarse"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">RICE</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dam_flour" in metrics_by_id:
        m = metrics_by_id["dam_flour"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">FLOUR</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "dam_lentil" in metrics_by_id:
        m = metrics_by_id["dam_lentil"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">LENTIL</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    hero_html = ""
    if "dam_rice_coarse" in metrics_by_id:
        hero = metrics_by_id["dam_rice_coarse"]
        # No threshold badge — V4 builder doesn't populate delta for mom-change check.
        hero_html = metric_hero_card(hero, badge=None, supporting="DAM weekly retail")

    supporting_cards = []
    for mid in ("dam_flour", "dam_lentil", "dam_oil"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="13",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_dam.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `657 passed in <N>s`.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_dam.py tests/render/v5/test_section_dam.py
git commit -m "feat(v5): add DAM section template (§13)

Hero: dam_rice_coarse. Supporting: flour, lentil, oil. Pills: RICE,
FLOUR, LENTIL. No threshold badge — V4 builder doesn't populate
Metric.delta for mom-change check.

5 unit tests including 'no badge ever' guard. Tests: 652 → 657."
```

---

## Task 6: Wire Wave 2 templates into the V5 dispatcher

**Files:**
- Modify: `brief/pipeline.py:646-668` (the V5 mode block in `render_index_html` — section_renderers dict + the import block)

**Goal:** Extend the `section_renderers` dict from 5 entries (bb + Wave 1) to 10 (bb + Wave 1 + Wave 2).

- [ ] **Step 1: Read the current dispatch block.**

```bash
sed -n '640,675p' brief/pipeline.py
```

Expected: shows the import block including `section_bb`, `section_fx`, `section_macro`, `section_nbr`, `section_remit`, and the `section_renderers` dict with those five entries.

- [ ] **Step 2: Apply the edit.**

In `brief/pipeline.py`, replace the existing Wave 1 import block:

```python
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_bb import render_section_bb
        from brief.render.v5.templates.section_fx import render_section_fx
        from brief.render.v5.templates.section_macro import render_section_macro
        from brief.render.v5.templates.section_nbr import render_section_nbr
        from brief.render.v5.templates.section_remit import render_section_remit
```

with:

```python
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_bb import render_section_bb
        from brief.render.v5.templates.section_comm import render_section_comm
        from brief.render.v5.templates.section_dam import render_section_dam
        from brief.render.v5.templates.section_dse import render_section_dse
        from brief.render.v5.templates.section_fiscal import render_section_fiscal
        from brief.render.v5.templates.section_fx import render_section_fx
        from brief.render.v5.templates.section_macro import render_section_macro
        from brief.render.v5.templates.section_nbr import render_section_nbr
        from brief.render.v5.templates.section_remit import render_section_remit
        from brief.render.v5.templates.section_tbond import render_section_tbond
```

(All ten imports alphabetical for stable diff hygiene.)

And replace the existing dict:

```python
        section_renderers: dict = {
            "bb": render_section_bb,
            "fx": render_section_fx,
            "macro": render_section_macro,
            "remit": render_section_remit,
            "nbr": render_section_nbr,
        }
```

with:

```python
        section_renderers: dict = {
            "bb": render_section_bb,
            "comm": render_section_comm,
            "dam": render_section_dam,
            "dse": render_section_dse,
            "fiscal": render_section_fiscal,
            "fx": render_section_fx,
            "macro": render_section_macro,
            "nbr": render_section_nbr,
            "remit": render_section_remit,
            "tbond": render_section_tbond,
        }
```

- [ ] **Step 3: Confirm `pipeline.py` imports resolve.**

```bash
python -c "from brief.pipeline import render_index_html; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Confirm a V5-mode dispatch works in process.**

```bash
python -c "
from brief.render.v5.templates.section_dse import render_section_dse
from brief.render.v5.templates.section_tbond import render_section_tbond
from brief.render.v5.templates.section_comm import render_section_comm
from brief.render.v5.templates.section_fiscal import render_section_fiscal
from brief.render.v5.templates.section_dam import render_section_dam
print('all five Wave 2 templates importable')
"
```

Expected: `all five Wave 2 templates importable`.

- [ ] **Step 5: Run the full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `657 passed in <N>s`. Same count as Task 5 — dispatch wiring isn't asserted by unit tests.

- [ ] **Step 6: Commit.**

```bash
git add brief/pipeline.py
git commit -m "feat(v5): wire DSE/T-Bond/Comm/Fiscal/DAM into V5 dispatcher

Extends the section_renderers dict in pipeline.py from 5 entries (bb +
Wave 1) to 10 (adds Wave 2 sections). After this commit, V5 mode renders
nine non-stub sections; only Wave 3 sections (Headlines, Iran War,
Banking, Exec) remain as v4-stub fallbacks.

Imports re-sorted alphabetically.

Tests: 657/657 (unchanged — dispatch wiring isn't asserted by unit tests)."
```

---

## Task 7: Local smoke render (user-gated)

**Goal:** Optional local smoke render to eyeball the five new sections in V5 shape. Real Claude calls (~$7-12). User decides whether to run.

- [ ] **Step 1: Stop and ask the user.**

Tell the user:
> "Wave 2 templates done locally. 657/657 tests passing. Three options for smoke render: (a) run it now (~$7-12 in real Claude calls); (b) skip smoke and ship the PR; (c) you run the smoke yourself. Which?"

Wait for explicit choice.

- [ ] **Step 2: If (a), run the smoke.**

```bash
mkdir -p /tmp/wave2-smoke
BRIEF_RENDERER=v5 python -m brief.cli run --artifacts-dir /tmp/wave2-smoke 2>&1 | tail -20
```

Expected: completes in 200-400 seconds, exits 0, deposits `index.html`.

- [ ] **Step 3: Verify v4-stub count.**

```bash
grep -c "section-v4-stub" /tmp/wave2-smoke/index.html
```

Expected: `4` (only Wave 3 sections — headlines, iranwar, banking, exec — should still be stubs). If `9`, dispatch wiring failed; if `0`, something rendered the stubs as real sections.

- [ ] **Step 4: Verify the five new sections rendered.**

```bash
for sid in dse tbond comm fiscal dam; do
  count=$(grep -c "id=\"section-${sid}\"" /tmp/wave2-smoke/index.html)
  echo "${sid}: ${count}"
done
```

Expected: each prints `1`.

- [ ] **Step 5: Open in the browser and eyeball.**

```bash
open /tmp/wave2-smoke/index.html
```

Inspect: each new section renders with hero + supporting cards, threshold badge appears only on tbond when 10y > 12% and on dse when breadth_pct < 30%, the "no badge" sections (comm, fiscal, dam) show no badge regardless of values.

- [ ] **Step 6: Record outcome (no commit).**

Read-only task.

---

## Task 8: Push and open PR (gated on user approval)

**Goal:** Push `feat/v5-wave2` and open PR #22 against `feat/v4-retarget`.

Shared-state action — needs explicit user approval per the user's standing rule.

- [ ] **Step 1: Stop and ask.**

> "Wave 2 done locally. 657/657 tests passing. Six commits on `feat/v5-wave2`. May I push to origin and open PR #22 against `feat/v4-retarget`?"

Wait for action-explicit approval.

- [ ] **Step 2: Push.**

```bash
git push -u origin feat/v5-wave2
```

- [ ] **Step 3: Open the PR.**

```bash
gh pr create --base feat/v4-retarget --head feat/v5-wave2 --title "feat(v5): Wave 2 — DSE, T-Bond, Comm, Fiscal, DAM section templates" --body "$(cat <<'EOF'
## Summary

V5 Plan B Wave 2 — five new section templates following the bb/Wave-1 scaffold:

- **§06 DSE** — hero `dse_dsex_close`; breadth_pct < 30 → WATCH (computed from advancing/declining)
- **§07 T-Bond** — hero `tbond_bond_10y`; 10y > 12% → WATCH
- **§10 Commodities** — hero `comm_gold_usd_oz`; no threshold (no brent in this builder)
- **§11 Fiscal** — hero `fiscal_nbr_collected_trn`; no threshold (no deficit metric)
- **§13 DAM** — hero `dam_rice_coarse`; no threshold (no delta in V4 builder)

Each template is a single function under 60 lines. The `section_renderers` dict in `pipeline.py` grows from 5 entries to 10. After merge, only Wave 3 sections (Headlines, Iran War, Banking, Exec) remain as v4-stub fallbacks.

### Spec deviations from §6 of the design doc

Same pattern as Wave 1 — the spec table was illustrative. Real metric IDs from V4 builders:

- DSE: `dsex_close`, `ds30`, `dses`, `turnover_crore`, `advancing`, `declining`, `dsex_change_pct`
- T-Bond: `tbill_91d/182d/364d`, `bond_5y`, `bond_10y`
- Comm: `gold_usd_oz`, `gold_22k_bdt`, `lng_jkm` (no brent — lives in iranwar)
- Fiscal: `nbr_collected_trn`, `nbr_target_trn`, `adp_pct`, `govt_borrow_trn`
- DAM: 9 weekly food-price metrics

Section numbers from `pipeline_v5._section_n`: dse=06, tbond=07, comm=10, fiscal=11, dam=13.

### Test plan

- [x] 5 unit tests per section × 5 sections = +25 tests; suite 632 → 657 passing
- [x] Each test file covers: full-metrics, no-metrics, no-news, threshold-badge (or "no badge" guard for comm/fiscal/dam), wrong-id ValueError
- [x] All five template modules under 65 lines
- [ ] Manual: local smoke render (per-PR decision; see Task 7 in plan)

### Out of scope

- Wave 3 (Headlines, Iran War, Banking, Exec) — separate PR, may need editorial fallbacks for sections without hero metrics
- Tiered model routing — parked
EOF
)"
```

- [ ] **Step 4: Verify PR state.**

```bash
gh pr view --json number,state,mergeable,baseRefName,headRefName,additions,deletions,changedFiles
```

Expected: `state=OPEN`, `mergeable=MERGEABLE`, `changedFiles=11` (5 templates + 5 tests + 1 modified pipeline.py).

---

## Acceptance criteria for PR #22

When all eight tasks are checked off:

- ✓ Five new files under `brief/render/v5/templates/`: `section_dse.py`, `section_tbond.py`, `section_comm.py`, `section_fiscal.py`, `section_dam.py` — each ≤65 lines.
- ✓ Five new test files under `tests/render/v5/`: `test_section_dse.py`, `test_section_tbond.py`, `test_section_comm.py`, `test_section_fiscal.py`, `test_section_dam.py` — each with 5 tests.
- ✓ `brief/pipeline.py` `section_renderers` dict has 10 entries.
- ✓ All 657 tests pass; no regression in the previous 632.
- ✓ Test suite runs in 15-40 seconds (proves no real Claude calls fired).
- ✓ Local smoke (Task 7) eyeballed and approved (or explicitly skipped).
- ✓ PR #22 open against `feat/v4-retarget`, MERGEABLE, CLEAN.

After PR #22 merges, Wave 3 plan-write begins (the trickiest wave — Headlines and Exec have no hero metrics, may need editorial fallbacks).
