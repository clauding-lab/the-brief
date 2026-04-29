# The Brief — V5 Plan B design

**Date:** 2026-04-29
**Author:** Adnan Rashid (with Claude)
**Status:** Approved (brainstorm complete; awaiting implementation plan via writing-plans skill)
**Predecessor:** [V5 design (Plan A)](./2026-04-25-the-brief-v5-design.md)

---

## 1. Goal

Extend the V5 magazine layout to the 13 sections currently rendering as `<section-v4-stub>` placeholders. After Plan B, every section in the brief renders in the V5 editorial shape pioneered by `bb` in Plan A.

**In scope:** 13 new section templates and the supporting refactor to keep the codebase under file-size limits.

**Out of scope:**
- New shared chrome (masthead, risk map, FOB, secondary grid, live banner, colophon — all built in Plan A)
- Tiered model routing (parked separately as a future improvement)
- Quality A/B between effort levels
- Re-enabling `brief.timer` on the VPS (separate cutover decision)
- New section data sources (the V4 builders already produce `SectionData`)

## 2. Decisions captured during brainstorm

1. **Section shape — strict uniformity.** Every Plan B section uses the exact bb scaffold: header (numeral / kicker / title / tldr / freshness + cadence pills) → 3 summary pills → optional systemic-risk callout → 4 metric cards (1 hero + 3 supporting) → optional sparkline → optional news block → optional banker's read. Sections without hero metrics (Headlines, Executive Signals) render with empty `metric_cards_html` and let the news block carry the weight — graceful fallback rather than custom shape.
2. **Three waves, not big-bang.** Each wave is its own PR, gated by local smoke + browser eyeball + sign-off. Order based on structural similarity to bb (highest-fit first, lowest-fit last).
3. **Pre-wave split is its own PR.** `brief/pipeline.py` is at 1,230 lines, over the 800-line soft cap. Add 13 more templates without splitting and the file balloons past 1,500. The split lands as the first PR in the Plan B series, before any new templates.
4. **Subagent-driven execution.** One section per subagent, dispatched in parallel where possible. Sonnet 4.6 floor (per user's standing rule). Each subagent gets the spec file, the bb reference, and the per-section parameters table from §6 of this document.
5. **TDD per section.** Five tests per file: full-metrics happy path, no-metrics fallback, no-news fallback, threshold badge, wrong-id ValueError. ~80 lines per test file.

## 3. Wave breakdown

| Wave | Sections | Rationale | Sessions est. |
|---|---|---|---|
| Pre-Wave (PR #20) | `pipeline.py` → `pipeline_v4.py` + `pipeline_v5.py` | Pre-emptive size split. No behavior change. | 1 |
| Wave 1 (PR #21) | FX, Macro, Remittance, NBR | Tier-1 banker reads with clean hero+supporting metric structure. Validates the bb pattern extends. | 2 |
| Wave 2 (PR #22) | DSE, T-Bonds, Commodities, DAM, Fiscal | Markets/numeric sections. Different data shape (price ladders, yield curves) but same scaffold. | 2 |
| Wave 3 (PR #23) | Headlines, Iran War & Oil, Banking, Executive Signals | Editorially-led. May surface fallback issues; budgeted with headroom. | 1-2 |

Total estimate: **6-7 sessions** for all 13 sections + the prerequisite split.

## 4. Architecture

### File layout after Plan B (changes only)

```
brief/
├── pipeline.py              # V4 logic + V5 dispatcher only            (~600 lines after split)
├── pipeline_v5.py           # NEW — V5 editorial pipeline               (~700 lines, Pre-Wave)
└── render/
    └── v5/
        ├── _section_base.py # SHARED scaffold (UNCHANGED)
        ├── assemble.py      # MODIFIED — dispatch table grows by 13
        └── templates/
            ├── section_bb.py           # existing
            ├── section_fx.py           # NEW Wave 1
            ├── section_macro.py        # NEW Wave 1
            ├── section_remit.py        # NEW Wave 1
            ├── section_nbr.py          # NEW Wave 1
            ├── section_dse.py          # NEW Wave 2
            ├── section_tbond.py        # NEW Wave 2
            ├── section_comm.py         # NEW Wave 2
            ├── section_dam.py          # NEW Wave 2
            ├── section_fiscal.py       # NEW Wave 2
            ├── section_headlines.py    # NEW Wave 3
            ├── section_iranwar.py      # NEW Wave 3
            ├── section_banking.py      # NEW Wave 3
            └── section_exec.py         # NEW Wave 3
```

### Dispatch table (new in `brief/render/v5/assemble.py`)

```python
_V5_TEMPLATE_DISPATCH = {
    "bb": render_section_bb,
    "fx": render_section_fx,
    "macro": render_section_macro,
    "remit": render_section_remit,
    "nbr": render_section_nbr,
    "dse": render_section_dse,
    "tbond": render_section_tbond,
    "comm": render_section_comm,
    "dam": render_section_dam,
    "fiscal": render_section_fiscal,
    "headlines": render_section_headlines,
    "iranwar": render_section_iranwar,
    "banking": render_section_banking,
    "exec": render_section_exec,
}

def _render_section_v5(section: SectionData) -> str:
    renderer = _V5_TEMPLATE_DISPATCH.get(section.id)
    if renderer is None:
        return _render_v4_stub(section)
    return renderer(section)
```

The `_render_v4_stub` fallback remains for safety — for any section ID not in the dispatch table.

### Data flow (unchanged from Plan A)

V4 builders → `SectionData` → V5 editorial pipeline (banker reads, systemic risks, QA) → V5 dispatch → per-section template → HTML. The Section Adapter (`_v5_apply_section_adapter`) continues to fill empty `kicker`/`tldr` fields where Claude calls didn't.

### What does NOT change

- `_section_base.py` — already supports the strict-uniformity contract; needs no edits.
- `_jsx.py` helpers — `metric_hero_card`, `news_bullet`, `freshness_pill`, `cadence_pill_v5`, `bankerread_panel_v5`, `systemic_risk_callout`, `sparkline_svg` already exist.
- Section schema (`brief/schema.py`) — unchanged.
- The 14 V4 builders — unchanged.
- All Claude prompts — unchanged.
- Cost / runtime profile — render layer is post-Claude; no impact on call costs.

## 5. Per-section template contract

Every new `section_<id>.py` follows the bb structure: ~30-50 lines, single function, takes `SectionData`, returns HTML.

```python
"""V5 §<NN> — <Section Title>."""
from __future__ import annotations

from brief.render.v5._jsx import _esc, fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_<id>(section: SectionData) -> str:
    if section.id != "<id>":
        raise ValueError(f"render_section_<id> received id={section.id!r}; expected '<id>'")

    metrics_by_id = {m.id: m for m in section.metrics}

    # 1. Summary pills — section-specific 2-3 metrics
    pills = []
    if "<primary_metric_id>" in metrics_by_id:
        m = metrics_by_id["<primary_metric_id>"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">{LABEL}</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

    # 2. Hero metric card
    hero_html = ""
    if "<hero_metric_id>" in metrics_by_id:
        hero = metrics_by_id["<hero_metric_id>"]
        badge = _section_threshold_badge(hero)  # optional
        hero_html = metric_hero_card(hero, badge=badge, supporting="<section-specific footer>")

    # 3. Supporting metric cards
    supporting_cards = []
    for mid in ("<m1>", "<m2>", "<m3>"):
        if mid in metrics_by_id:
            supporting_cards.append(metric_hero_card(metrics_by_id[mid]))
    metric_cards_html = hero_html + "".join(supporting_cards)

    # 4. News block
    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="<NN>",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

## 6. Per-section parameters

The implementation plan derives concrete metric IDs from `brief/schema.py`. The table below is the design intent; metric IDs are illustrative and the implementation plan must verify each ID exists in the schema before use.

| Section | §NN | Hero metric | Supporting (3) | Pills (2-3) | Sparkline | Threshold badge |
|---|---|---|---|---|---|---|
| **fx** | 03 | `fx_usd_bdt` | NEER, REER, gross_reserves | USD/BDT, RESERVES, RUNWAY | yes | reserves < $32B → CRITICAL, < $34B → WATCH |
| **macro** | 04 | `cpi_general` | core_cpi, food_cpi, fuel_cpi | CPI, CORE, FOOD | yes | cpi > 10% → CRITICAL |
| **remit** | 05 | `remit_monthly_inflow` | wires, MTOs, yoy_pct | MONTHLY, YoY%, RUNRATE | yes | yoy < −5% → WATCH |
| **nbr** | 06 | `nbr_monthly_collection` | yoy_pct, fytd_pct, vs_target | MONTHLY, FYTD, TARGET% | yes | fytd < 95% → WATCH |
| **dse** | 07 | `dsex_close` | breadth_pct, turnover, sector_heat | DSEX, BREADTH, TURNOVER | yes | breadth < 30% → WATCH |
| **tbond** | 09 | `tb_10y` | tb_5y, tb_2y, repo_rate | 10Y, 2Y, REPO | yes | 10y > 12% → WATCH |
| **comm** | 10 | `crude_brent` | gold, wheat, copper | BRENT, GOLD, WHEAT | yes | brent > $90 → WATCH |
| **dam** | 11 | `rice_coarse` | wheat_flour, lentil, soy_oil | RICE, WHEAT, LENTIL | yes | rice > +10% mom → WATCH |
| **fiscal** | 12 | `fy_deficit_ratio` | revenue_pct, spending_pct, dom_borrowing | DEFICIT, REV%, BORROW | yes | deficit > 5% → WATCH |
| **headlines** | 01 | (no hero — news drives) | (empty) | (empty) | no | n/a |
| **iranwar** | 08 | `crude_brent` | gold, dxy, gas_henry_hub | BRENT, GOLD, DXY | yes | brent > $100 → CRITICAL |
| **banking** | 13 | `npl_ratio` | car_ratio, ldr_ratio, deposits_yoy | NPL, CAR, LDR | no | npl > 12% → WATCH |
| **exec** | 14 | (no hero — signals drive) | (empty) | (empty) | no | n/a |

## 7. Testing strategy

### Per-section unit tests

`tests/render/v5/test_section_<id>.py` — five tests each:

| Test | Assertion target |
|---|---|
| `test_render_section_<id>_with_full_metrics` | kicker, tldr, 3 pills, hero card, 3 supporting cards, 3 news bullets all in HTML |
| `test_render_section_<id>_with_no_metrics` | empty `metric_cards_html` does not break render (no orphan grid wrapper) |
| `test_render_section_<id>_with_no_news` | news block omitted, no orphan `<ul class="sec-news">` |
| `test_render_section_<id>_with_threshold_badge` | hero card carries `CRITICAL` or `WATCH` badge per threshold logic |
| `test_render_section_<id>_rejects_wrong_id` | `ValueError` raised when called with a `SectionData` whose `id` does not match |

### Acceptance counts

- Pre-Wave: 0 new tests (refactor only); existing 612 stay green.
- Wave 1: +20 tests → 632.
- Wave 2: +25 tests → 657.
- Wave 3: +20 tests → 677.

### Smoke validation per wave PR

- Local smoke render at $7-12 per run, depending on whether all banker reads fire.
- Browser eyeball of the HTML output — every new section reviewed visually before PR merge.
- VPS smoke only when something pipeline-touching changes (none expected in pure render-layer work).

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hero shape doesn't fit `metric_hero_card` for some section | Medium | Forces per-section helper or shape divergence | Wave 3 surfaces this first (Headlines, Exec). If real, add one new shared helper, not a custom shape. |
| Subagent produces wrong CSS class names | Low | Visual regression | Tests pin class names; subagent PR fails CI. |
| "Graceful fallback" looks bad for empty-metric sections | Medium | Visual quality miss in Wave 3 | Eyeball after first Wave 3 section. If poor, add an opt-in `news-led` flag to `_section_base.py`. |
| Pre-Wave split breaks an import path | Low | Tests fail | Full suite catches; V5 dispatch test pins behavior. |
| Metric IDs in §6 don't match `brief/schema.py` reality | Medium | Subagent renders with empty cards | Implementation plan must include a schema-cross-check step before subagent dispatch. |
| Test count creep — 5 × 13 = 65 tests, but some sections need 6 or 7 | Low | Minor; tests are cheap | Allow per-section test count flexibility. |

## 9. Acceptance for full Plan B

When all three waves are merged into `feat/v5-pilot` (or a successor branch):

- 677 / 677 tests passing
- 0 `<section-v4-stub>` markers in any V5 HTML render
- Local smoke renders all 14 sections in V5 shape
- VPS smoke renders cleanly (no Claude CLI errors, no template errors)
- All 13 sections individually eyeballed and approved
- PRs #20, #21, #22, #23 all merged

## 10. Out-of-scope notes (parked for future)

- **Tiered model routing per V5 call** — Sonnet for Tier-2 banker reads, Opus for Tier-1, projected ~36% cost saving. Plan exists in conversation/session history; revisit after Plan B ships.
- **A/B effort calibration** — high vs xhigh quality comparison; relevant once VPS CLI is upgraded to v2.1.119+.
- **Per-builder kicker/tldr** instead of the centralized adapter — cleaner long-term ownership but higher touch count. Adapter remains the pragmatic Plan B home.
- **Re-enable `brief.timer`** on VPS — separate operational decision once Plan B merges and the V5 daily render is trusted.
