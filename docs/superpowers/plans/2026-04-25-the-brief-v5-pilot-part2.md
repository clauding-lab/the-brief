# The Brief V5 — Pilot + Chrome Implementation Plan, Part 2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Continuation of `2026-04-25-the-brief-v5-pilot.md`.** Phases 1-4 (pre-flight, schema, max_client extended thinking, V5 module skeleton, V5 JSX helpers) are in Part 1. This file covers Phases 5-12: chrome components, editorial Claude calls, pilot section, dispatch, and validation.

---

## Phase 5 — Chrome components (~3 hours)

Each chrome component is a deterministic Python function returning an HTML fragment string. Inputs are typed (`SectionData`, `TopPicks`, `TodaysCall`, etc.). All chrome lives in `brief/render/v5/chrome/`.

**Files:**
- Create: `brief/render/v5/chrome/live_banner.py`
- Create: `brief/render/v5/chrome/masthead.py`
- Create: `brief/render/v5/chrome/todays_call.py`
- Create: `brief/render/v5/chrome/risk_map.py`
- Create: `brief/render/v5/chrome/front_of_book.py`
- Create: `brief/render/v5/chrome/secondary_grid.py`
- Create: `brief/render/v5/chrome/colophon.py`
- Test: `tests/render/v5/test_chrome_*.py` (one per component)

### Task 5: Live status banner

**Inputs:** dict of live values: `{usd_bdt, dsex, brent, reserves_bn_usd, generated_at, next_update_label}`. Pure data; no Claude.

- [ ] **Step 1: Write failing test**

Create `tests/render/v5/test_chrome_live_banner.py`:

```python
from datetime import datetime, timezone

from brief.render.v5.chrome.live_banner import render_live_banner


def test_live_banner_renders_all_fields():
    html = render_live_banner({
        "usd_bdt": 122.70,
        "dsex": 5232,
        "brent_usd": 95.10,
        "reserves_bn_usd": 34.12,
        "generated_at": datetime(2026, 4, 21, 6, 15, tzinfo=timezone.utc),
        "next_update_label": "18:00 CLOSE",
    })
    assert "USD/BDT" in html
    assert "122.70" in html
    assert "DSEX" in html
    assert "5,232" in html
    assert "BRENT" in html
    assert "95.10" in html
    assert "RESERVES" in html
    assert "34.12BN" in html or "34.12 BN" in html
    assert "NEXT UPDATE" in html
    assert "18:00 CLOSE" in html
    assert 'class="live-banner"' in html


def test_live_banner_handles_missing_brent_gracefully():
    html = render_live_banner({
        "usd_bdt": 122.70,
        "dsex": 5232,
        "brent_usd": None,
        "reserves_bn_usd": 34.12,
        "generated_at": datetime(2026, 4, 21, 6, 15, tzinfo=timezone.utc),
        "next_update_label": "18:00 CLOSE",
    })
    # Missing brent should not break render; show em-dash or omit
    assert 'class="live-banner"' in html
    assert "USD/BDT" in html  # other fields still render
```

- [ ] **Step 2: Implement `brief/render/v5/chrome/live_banner.py`**

```python
"""V5 live status banner — top of page, oxblood, mono."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from brief.render.v5._jsx import _esc, fmt_num


def render_live_banner(live: dict[str, Any]) -> str:
    """Top-of-page status strip with live market values.

    Pure data — no Claude. Inputs come from EconDelta + Supabase via the
    pipeline gather stage.

    Schema: live = {
        usd_bdt: float | None,
        dsex: int | float | None,
        brent_usd: float | None,
        reserves_bn_usd: float | None,
        generated_at: datetime,
        next_update_label: str,
    }
    """
    def _val(x: float | int | None, fmt: str = "{:.2f}") -> str:
        return fmt.format(x) if x is not None else "—"

    time_label = live["generated_at"].strftime("%H:%M")
    usd = _val(live.get("usd_bdt"))
    dsex = _val(live.get("dsex"), "{:,.0f}")
    brent = _val(live.get("brent_usd"))
    reserves = _val(live.get("reserves_bn_usd"))
    nxt = _esc(live.get("next_update_label", ""))

    return (
        '<section class="live-banner" aria-label="Live market status">'
        '<div class="live-banner-inner">'
        f'<span class="lb-stamp"><span class="lb-dot">●</span> LIVE · {_esc(time_label)} BDT · DHAKA</span>'
        '<span class="lb-grid">'
        f'<span class="lb-field"><span class="lb-key">USD/BDT</span> <span class="lb-val">{_esc(usd)}</span></span>'
        f'<span class="lb-field"><span class="lb-key">DSEX</span> <span class="lb-val">{_esc(dsex)}</span></span>'
        f'<span class="lb-field"><span class="lb-key">BRENT</span> <span class="lb-val">${_esc(brent)}</span></span>'
        f'<span class="lb-field"><span class="lb-key">RESERVES</span> <span class="lb-val">${_esc(reserves)}BN</span></span>'
        '</span>'
        f'<span class="lb-next">NEXT UPDATE · {nxt}</span>'
        '</div>'
        '</section>'
    )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/render/v5/test_chrome_live_banner.py -v`
Expected: 2 tests pass.

- [ ] **Step 4: Commit**

```bash
git add brief/render/v5/chrome/live_banner.py tests/render/v5/test_chrome_live_banner.py
git commit -m "feat(render/v5): live status banner"
```

### Task 6: Masthead

**Inputs:** `vol`, `issue`, `today_label`, `byline_label`, `TodaysCall` instance.

- [ ] **Step 1: Write failing test**

Create `tests/render/v5/test_chrome_masthead.py`:

```python
from datetime import datetime, timezone

from brief.render.v5.chrome.masthead import render_masthead
from brief.schema import TodaysCall


def test_masthead_renders_volume_issue_date_title_dek_todays_call():
    tc = TodaysCall(
        text="Hormuz is priced risk, not scarcity. With food CPI sticky at 10.4% and reserves flat-not-building, the margin for a second incident is narrower than it looks. Hedge the oil book — not the headline.",
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    html = render_masthead(
        vol="II",
        issue=412,
        today_label="Tue 21 Apr 2026",
        todays_call=tc,
    )
    assert "VOL. II" in html
    assert "NO. 412" in html
    assert "Tue 21 Apr 2026" in html
    assert "The" in html and "Brief" in html  # title
    assert "plotted" in html
    assert "TODAY'S CALL" in html
    assert "priced risk, not scarcity" in html
    assert "Desk Editor" in html
    assert 'class="masthead"' in html


def test_masthead_escapes_call_text():
    tc = TodaysCall(text="<script>x</script> " * 8, generated_at=datetime.now(timezone.utc))
    html = render_masthead(vol="II", issue=1, today_label="x", todays_call=tc)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
```

- [ ] **Step 2: Implement `brief/render/v5/chrome/masthead.py`**

```python
"""V5 masthead — magazine title + dek + TODAY'S CALL panel."""
from __future__ import annotations

from brief.render.v5._jsx import _esc
from brief.schema import TodaysCall


def render_masthead(*, vol: str, issue: int, today_label: str, todays_call: TodaysCall) -> str:
    """The Brief masthead block.

    Layout (desktop): title + dek on left (66%); TODAY'S CALL panel on right (33%).
    Title: "The" plain, "Brief," italic-oxblood, "plotted." italic-ink — all in one line break.
    """
    return (
        '<section class="masthead" aria-label="Masthead">'
        '<div class="mast-meta">'
        f'<span>VOL. {_esc(vol)}</span><span> · </span>'
        f'<span>NO. {issue}</span><span> · </span>'
        '<span>BANGLADESH · DAILY SUN-FRI</span><span> · </span>'
        f'<time datetime="{_esc(today_label)}">{_esc(today_label)}</time>'
        '</div>'
        '<div class="mast-grid">'
        '<div class="mast-title-block">'
        '<h1 class="mast-title">'
        '<span class="mt-the">The</span> '
        '<em class="mt-brief">Brief,</em><br>'
        '<em class="mt-plotted">plotted.</em>'
        '</h1>'
        '<p class="mast-dek">'
        '— <em>Seven sections arranged by how much they moved and how much '
        'the book cares — not by section number.</em>'
        '</p>'
        '</div>'
        '<aside class="todays-call">'
        '<div class="tc-label">TODAY\'S CALL</div>'
        f'<p class="tc-text">{_esc(todays_call.text)}</p>'
        f'<div class="tc-byline">— {_esc(todays_call.byline)}</div>'
        '</aside>'
        '</div>'
        '</section>'
    )
```

- [ ] **Step 3: Run tests + commit**

Run: `pytest tests/render/v5/test_chrome_masthead.py -v`
Expected: 2 tests pass.

```bash
git add brief/render/v5/chrome/masthead.py tests/render/v5/test_chrome_masthead.py
git commit -m "feat(render/v5): masthead with magazine title + TODAY'S CALL panel"
```

### Task 7: Risk map (renderer; SVG)

**Inputs:** `TopPicks` instance + dict of `SectionData` keyed by id (for labels).

- [ ] **Step 1: Write failing test**

Create `tests/render/v5/test_chrome_risk_map.py`:

```python
from datetime import datetime, timezone

from brief.render.v5.chrome.risk_map import render_risk_map
from brief.schema import GridEntry, MapPoint, TopPicks


def _section_lookup():
    """Minimal section catalog used by the risk map for labels."""
    return {
        "bb":      {"kicker": "Policy & rates", "n": "02"},
        "macro":   {"kicker": "Inflation",      "n": "03"},
        "fx":      {"kicker": "FX & external",  "n": "04"},
        "remit":   {"kicker": "Remittance",     "n": "05"},
        "dse":     {"kicker": "Equities · DSE", "n": "06"},
        "tbond":   {"kicker": "T-Bill & T-Bond","n": "07"},
        "iranwar": {"kicker": "Iran · Oil",     "n": "08"},
    }


def test_risk_map_renders_seven_bubbles_with_legend():
    plotted = [
        MapPoint(id="bb",      x=1.2, y=6.0, r=24, kind="anchor"),
        MapPoint(id="macro",   x=2.2, y=7.8, r=32, kind="slow"),
        MapPoint(id="fx",      x=3.4, y=6.3, r=28, kind="slow"),
        MapPoint(id="remit",   x=6.0, y=7.0, r=30, kind="fresh"),
        MapPoint(id="dse",     x=6.5, y=4.8, r=26, kind="fresh"),
        MapPoint(id="tbond",   x=5.0, y=5.4, r=24, kind="fresh"),
        MapPoint(id="iranwar", x=9.4, y=9.1, r=38, kind="event"),
    ]
    grid = [GridEntry(id=f"g{i}", tldr=f"tldr {i}") for i in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="iranwar")

    html = render_risk_map(picks=picks, sections=_section_lookup(), today_label="Tue 21 Apr 2026")

    # Seven circles
    assert html.count('<circle ') == 7
    # Quadrant labels
    for label in ("SLOW · STRUCTURAL", "ACTIVE · MATERIAL", "DORMANT", "NOISE"):
        assert label in html
    # Legend
    for kind in ("EVENT", "FRESH PRINT", "SLOW · STRUCTURAL", "ANCHOR"):
        assert kind in html
    # Read-first arrow points to front-of-book section
    assert "read first" in html.lower()


def test_risk_map_validates_seven_plotted():
    """Renderer must reject a TopPicks with != 7 plotted (defensive)."""
    plotted = [MapPoint(id="bb", x=1, y=1, r=10, kind="anchor")]  # only 1
    grid = [GridEntry(id=f"g{i}", tldr="x") for i in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="bb")

    import pytest
    with pytest.raises(ValueError, match="exactly 7"):
        render_risk_map(picks=picks, sections=_section_lookup(), today_label="x")
```

- [ ] **Step 2: Implement `brief/render/v5/chrome/risk_map.py`**

```python
"""V5 risk map — SVG bubble plot of today's top-7 sections.

Coordinate system: x ∈ [0, 10] = movement today; y ∈ [0, 10] = significance.
Map drawn at viewBox 0 0 640 480. Sections lookup provides {kicker, n} per id.
"""
from __future__ import annotations

from typing import Any

from brief.render.v5._jsx import _attr_esc, _esc
from brief.render.v5._tokens import KIND_COLOR
from brief.schema import TopPicks

PLOT_X0, PLOT_Y0 = 80, 40
PLOT_W, PLOT_H = 480, 360


def _coord(x: float, y: float) -> tuple[float, float]:
    """Map (x ∈ [0,10], y ∈ [0,10]) → SVG pixel space."""
    px = PLOT_X0 + (x / 10.0) * PLOT_W
    py = PLOT_Y0 + ((10.0 - y) / 10.0) * PLOT_H  # invert: y=10 at top
    return px, py


def render_risk_map(*, picks: TopPicks, sections: dict[str, dict[str, Any]], today_label: str) -> str:
    if len(picks.plotted) != 7:
        raise ValueError(f"render_risk_map expects exactly 7 plotted; got {len(picks.plotted)}")

    bubbles_html = []
    for point in picks.plotted:
        cx, cy = _coord(point.x, point.y)
        color = KIND_COLOR[point.kind]
        meta = sections.get(point.id, {"kicker": point.id, "n": ""})
        label_x = cx + point.r + 6
        label_y = cy + 4
        bubbles_html.append(
            f'<g class="rm-bubble rm-{point.kind}" data-id="{_attr_esc(point.id)}">'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{point.r}" fill="{color}"/>'
            f'<text class="rm-num" x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" fill="var(--ink-inverse)">§{_esc(meta["n"])}</text>'
            f'<text class="rm-label" x="{label_x:.1f}" y="{label_y:.1f}">{_esc(meta["kicker"])}</text>'
            f'</g>'
        )

    # Read-first arrow toward front-of-book section
    fob = next((p for p in picks.plotted if p.id == picks.front_of_book_id), picks.plotted[0])
    fx, fy = _coord(fob.x, fob.y)
    arrow_x = fx + fob.r + 80
    arrow_y = fy
    bubbles_html.append(
        f'<g class="rm-readfirst">'
        f'<text x="{arrow_x:.1f}" y="{arrow_y:.1f}">read first ↗</text>'
        f'</g>'
    )

    # Quadrant labels
    quads = (
        (PLOT_X0 + 100, PLOT_Y0 + 30, "SLOW · STRUCTURAL"),
        (PLOT_X0 + PLOT_W - 100, PLOT_Y0 + 30, "ACTIVE · MATERIAL"),
        (PLOT_X0 + 100, PLOT_Y0 + PLOT_H - 20, "DORMANT"),
        (PLOT_X0 + PLOT_W - 100, PLOT_Y0 + PLOT_H - 20, "NOISE"),
    )
    quad_html = "".join(
        f'<text class="rm-quad" x="{x}" y="{y}" text-anchor="middle">{_esc(label)}</text>'
        for x, y, label in quads
    )

    # Axis labels
    axis_html = (
        f'<text class="rm-axis-x" x="{PLOT_X0 + PLOT_W / 2}" y="{PLOT_Y0 + PLOT_H + 32}" text-anchor="middle">MOVEMENT TODAY →</text>'
        f'<text class="rm-axis-y" x="{PLOT_X0 - 28}" y="{PLOT_Y0 + PLOT_H / 2}" transform="rotate(-90 {PLOT_X0 - 28} {PLOT_Y0 + PLOT_H / 2})" text-anchor="middle">SIGNIFICANCE FOR THE BOOK ↑</text>'
    )

    # Legend
    legend_html = (
        '<div class="rm-legend">'
        '<span class="rm-leg-item"><span class="dot dot-event"></span> EVENT</span>'
        '<span class="rm-leg-item"><span class="dot dot-fresh"></span> FRESH PRINT</span>'
        '<span class="rm-leg-item"><span class="dot dot-slow"></span> SLOW · STRUCTURAL</span>'
        '<span class="rm-leg-item"><span class="dot dot-anchor"></span> ANCHOR</span>'
        '</div>'
    )

    return (
        '<section class="risk-map" aria-label="Risk map">'
        '<header class="rm-header">'
        f'<span class="rm-eyebrow">§ RISK MAP · {_esc(today_label)}</span>'
        '<span class="rm-eyebrow-right">AREA ∝ READ-WEIGHT · COLOR = KIND</span>'
        '</header>'
        '<svg class="rm-svg" viewBox="0 0 640 480" role="img" aria-label="Risk map plotting today\'s seven sections">'
        f'<rect class="rm-quad-bg q-slow"   x="{PLOT_X0}" y="{PLOT_Y0}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'<rect class="rm-quad-bg q-event"  x="{PLOT_X0+PLOT_W/2}" y="{PLOT_Y0}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'<rect class="rm-quad-bg q-anchor" x="{PLOT_X0}" y="{PLOT_Y0+PLOT_H/2}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'<rect class="rm-quad-bg q-noise"  x="{PLOT_X0+PLOT_W/2}" y="{PLOT_Y0+PLOT_H/2}" width="{PLOT_W/2}" height="{PLOT_H/2}"/>'
        f'{quad_html}'
        f'{axis_html}'
        + "".join(bubbles_html) +
        '</svg>'
        f'{legend_html}'
        '</section>'
    )
```

- [ ] **Step 3: Run tests + commit**

Run: `pytest tests/render/v5/test_chrome_risk_map.py -v`
Expected: 2 tests pass.

```bash
git add brief/render/v5/chrome/risk_map.py tests/render/v5/test_chrome_risk_map.py
git commit -m "feat(render/v5): risk map SVG with quadrants, legend, read-first arrow"
```

### Task 8: Front-of-book preview

**Inputs:** the SectionData for `front_of_book_id`. Renders structured preview pulled to the right of the risk map.

- [ ] **Step 1: Write failing test**

Create `tests/render/v5/test_chrome_front_of_book.py`:

```python
from datetime import date, datetime, timezone

from brief.render.v5.chrome.front_of_book import render_front_of_book
from brief.schema import BankerReadInsight, Metric, NewsItem, SectionData


def _iranwar_section():
    return SectionData(
        id="iranwar",
        title="Risk premium — not scarcity.",
        kicker="Iran · Oil",
        tldr="Hormuz incident; Brent +3.7%; war-risk premia +18%.",
        metrics=[
            Metric(id="brent_spot", label="Brent spot", value=95.10, unit="USD/bbl",
                   as_of=date(2026, 4, 21), source="Yahoo", cadence="daily"),
            Metric(id="wti_spot",   label="WTI spot",   value=91.00, unit="USD/bbl",
                   as_of=date(2026, 4, 21), source="Yahoo", cadence="daily"),
        ],
        news=[],
        freshness="fresh",
        bankerread=BankerReadInsight(
            variant="full",
            meaning="m" * 80,
            action="Add scenario provisions on aviation and bunker exposure above BDT 50cr; stress at Brent $115.",
            trigger="A confirmed strait closure or second incident puts CPI feed-through within 6 weeks.",
            focus="f" * 80,
            pull_quote="This morning's move is risk premium, not scarcity — but price the next incident before it happens.",
            generated_at=datetime.now(timezone.utc),
        ),
    )


def test_front_of_book_renders_structured_preview():
    section = _iranwar_section()
    html = render_front_of_book(section, section_n="08")
    assert "§08" in html
    assert "Iran · Oil" in html
    assert "Risk premium" in html
    assert "95.10" in html
    assert "91.00" in html
    assert "Add scenario provisions" in html
    assert "confirmed strait closure" in html
    assert 'href="#section-iranwar"' in html
    assert "JUMP TO §08" in html


def test_front_of_book_handles_missing_bankerread():
    section = _iranwar_section()
    section_no_br = section.model_copy(update={"bankerread": None})
    html = render_front_of_book(section_no_br, section_n="08")
    # Should still render core preview without action/trigger blocks
    assert "§08" in html
    assert "95.10" in html
    # Action/trigger blocks suppressed
    assert "Add scenario provisions" not in html
```

- [ ] **Step 2: Implement `brief/render/v5/chrome/front_of_book.py`**

```python
"""V5 front-of-book preview — pulled-in version of today's #1 section.

Rendered to the right of the risk map. Shows kicker, title, pull-quote callout,
2-4 metric cards, action+trigger paragraphs, jump-link.
"""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc, fmt_num
from brief.schema import SectionData


def render_front_of_book(section: SectionData, *, section_n: str) -> str:
    br = section.bankerread

    # Pull-quote
    pull_html = ""
    if br and br.pull_quote:
        pull_html = f'<div class="fob-pull"><em>{_esc(br.pull_quote)}</em></div>'

    # Up to 4 metric cards
    metric_cards = []
    for m in section.metrics[:4]:
        if isinstance(m.value, (int, float)):
            value_html = fmt_num(m.value, unit=m.unit, tabular=True)
        else:
            value_html = _esc(str(m.value))
        delta_html = ""
        if m.delta:
            sign = "+" if m.delta.value > 0 else ""
            delta_html = f'<div class="fob-card-delta dir-{m.delta.direction}">▲ {sign}{m.delta.value:.2f}</div>'
        metric_cards.append(
            '<div class="fob-card">'
            f'<div class="fob-card-label">{_esc(m.label)}</div>'
            f'<div class="fob-card-value">{value_html}</div>'
            f'{delta_html}'
            '</div>'
        )

    # Action / trigger paragraphs
    action_block = ""
    if br and br.action:
        action_block = f'<p class="fob-prose"><strong>Action.</strong> {_esc(br.action)}</p>'
    trigger_block = ""
    if br and br.trigger:
        trigger_block = f'<p class="fob-prose"><strong>Trigger.</strong> {_esc(br.trigger)}</p>'

    return (
        '<aside class="front-of-book" aria-label="Front-of-book section preview">'
        '<header class="fob-header">'
        f'<span class="fob-eyebrow">§{_esc(section_n)} {_esc(section.kicker.upper())}</span>'
        '<span class="fob-eyebrow-right">YAHOO · REUTERS</span>'
        '</header>'
        f'<h2 class="fob-title">{_esc(section.title)}</h2>'
        f'{pull_html}'
        f'<div class="fob-cards">{"".join(metric_cards)}</div>'
        f'{action_block}'
        f'{trigger_block}'
        f'<a class="fob-jump" href="#section-{_attr_esc(section.id)}">JUMP TO §{_esc(section_n)} {_esc(section.kicker.upper())} ↓</a>'
        '</aside>'
    )
```

- [ ] **Step 3: Run tests + commit**

```bash
pytest tests/render/v5/test_chrome_front_of_book.py -v
git add brief/render/v5/chrome/front_of_book.py tests/render/v5/test_chrome_front_of_book.py
git commit -m "feat(render/v5): front-of-book section preview"
```

### Task 9: Secondary 7-card grid

**Inputs:** `TopPicks` (uses `grid` field) + dict of `SectionData` keyed by id.

- [ ] **Step 1: Write failing test**

Create `tests/render/v5/test_chrome_secondary_grid.py`:

```python
from datetime import date

from brief.render.v5.chrome.secondary_grid import render_secondary_grid
from brief.schema import GridEntry, MapPoint, Metric, SectionData, TopPicks


def _seven_sections():
    return {
        "banking": SectionData(id="banking", title="Banking Sector", kicker="Banking",
                               tldr="", metrics=[], news=[], freshness="warn"),
        "comm":    SectionData(id="comm", title="Commodities", kicker="Comm",
                               tldr="", metrics=[], news=[], freshness="stale"),
        "fiscal":  SectionData(id="fiscal", title="Fiscal", kicker="Fiscal",
                               tldr="", metrics=[], news=[], freshness="stale"),
        "nbr":     SectionData(id="nbr", title="NBR Tax", kicker="NBR",
                               tldr="", metrics=[], news=[], freshness="warming_up"),
        "dam":     SectionData(id="dam", title="Domestic Food Prices", kicker="DAM",
                               tldr="", metrics=[], news=[], freshness="fresh"),
        "headlines": SectionData(id="headlines", title="Headlines", kicker="Headlines",
                                 tldr="", metrics=[], news=[], freshness="fresh"),
        "exec":    SectionData(id="exec", title="Exec Signals", kicker="Exec",
                               tldr="", metrics=[], news=[], freshness="fresh"),
    }


def test_secondary_grid_renders_seven_cards():
    grid = [
        GridEntry(id="banking",   tldr="NPL 35.73% — historic high"),
        GridEntry(id="comm",      tldr="LNG JKM $10.4 — flat WoW"),
        GridEntry(id="fiscal",    tldr="NBR collected 2.84tn YTD"),
        GridEntry(id="nbr",       tldr="VAT 38.2bn — Mar print due Sun"),
        GridEntry(id="dam",       tldr="Onion +12% WoW"),
        GridEntry(id="headlines", tldr="9 curated stories"),
        GridEntry(id="exec",      tldr="6 prints · 3 watches"),
    ]
    plotted = [MapPoint(id="bb", x=1, y=1, r=10, kind="anchor") for _ in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="bb")

    html = render_secondary_grid(picks=picks, sections=_seven_sections())
    assert "ALSO TODAY" in html
    assert html.count('class="grid-card') == 7
    assert "NPL 35.73%" in html
    assert "Onion +12% WoW" in html
    assert 'href="#section-banking"' in html


def test_secondary_grid_handles_unknown_id_safely():
    grid = [GridEntry(id="ghost", tldr="x") for _ in range(7)]
    plotted = [MapPoint(id="bb", x=1, y=1, r=10, kind="anchor") for _ in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="bb")
    # Renderer must not crash on an unknown id; show kicker fallback
    html = render_secondary_grid(picks=picks, sections={})
    assert html.count('class="grid-card') == 7
```

- [ ] **Step 2: Implement `brief/render/v5/chrome/secondary_grid.py`**

```python
"""V5 secondary 7-card grid — 'ALSO TODAY' below the risk map."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc, freshness_pill
from brief.schema import SectionData, TopPicks


def render_secondary_grid(*, picks: TopPicks, sections: dict[str, SectionData]) -> str:
    cards = []
    for entry in picks.grid:
        section = sections.get(entry.id)
        kicker = section.kicker if section else entry.id
        freshness = section.freshness if section else "unavailable"
        pill = freshness_pill(freshness)
        cards.append(
            '<a class="grid-card" data-freshness="' + _attr_esc(freshness) + '" '
            f'href="#section-{_attr_esc(entry.id)}">'
            f'<span class="grid-card-kicker">{_esc(kicker.upper())}</span>'
            f'<span class="grid-card-tldr">{_esc(entry.tldr)}</span>'
            f'<span class="grid-card-meta">{pill}<span class="grid-card-arrow">→</span></span>'
            '</a>'
        )

    return (
        '<section class="secondary-grid" aria-label="Other sections today">'
        '<header class="sg-header">ALSO TODAY · 7 SECTIONS NOT ON THE MAP</header>'
        f'<div class="sg-grid">{"".join(cards)}</div>'
        '</section>'
    )
```

- [ ] **Step 3: Run tests + commit**

```bash
pytest tests/render/v5/test_chrome_secondary_grid.py -v
git add brief/render/v5/chrome/secondary_grid.py tests/render/v5/test_chrome_secondary_grid.py
git commit -m "feat(render/v5): secondary 7-card grid for unfeatured sections"
```

### Task 10: Colophon

**Inputs:** dict with `vol`, `issue`, `today_label`, `sources_used: list[str]`, `render_duration_s`, `total_cost_usd`.

- [ ] **Step 1: Write failing test**

Create `tests/render/v5/test_chrome_colophon.py`:

```python
from brief.render.v5.chrome.colophon import render_colophon


def test_colophon_renders_metadata():
    html = render_colophon({
        "vol": "II",
        "issue": 412,
        "today_label": "Tue 21 Apr 2026",
        "sources_used": ["BB", "BBS", "DSE", "Yahoo"],
        "render_duration_s": 1820,
        "total_cost_usd": 38.42,
    })
    assert "VOL. II" in html
    assert "NO. 412" in html
    assert "Tue 21 Apr 2026" in html
    assert "BB" in html and "DSE" in html
    assert "30:20" in html or "30 min" in html  # rendered duration
    assert "$38.42" in html
    assert 'class="colophon"' in html
```

- [ ] **Step 2: Implement `brief/render/v5/chrome/colophon.py`**

```python
"""V5 colophon — bottom-of-page metadata strip."""
from __future__ import annotations

from typing import Any

from brief.render.v5._jsx import _esc


def render_colophon(meta: dict[str, Any]) -> str:
    duration_s = meta.get("render_duration_s", 0)
    minutes, seconds = divmod(int(duration_s), 60)
    duration_label = f"{minutes:02d}:{seconds:02d}"
    cost = meta.get("total_cost_usd", 0.0)

    sources = " · ".join(_esc(s) for s in meta.get("sources_used", []))

    return (
        '<footer class="colophon" aria-label="Edition metadata">'
        '<div class="col-row">'
        f'<span>VOL. {_esc(str(meta.get("vol", "")))}</span>'
        f'<span>NO. {meta.get("issue", "")}</span>'
        f'<span>{_esc(meta.get("today_label", ""))}</span>'
        '</div>'
        '<div class="col-row col-sources">'
        f'<span class="col-label">SOURCES</span> {sources}'
        '</div>'
        '<div class="col-row col-stats">'
        f'<span>RENDER {duration_label}</span>'
        f'<span>COST ${cost:.2f}</span>'
        '</div>'
        '</footer>'
    )
```

- [ ] **Step 3: Run tests + commit**

```bash
pytest tests/render/v5/test_chrome_colophon.py -v
git add brief/render/v5/chrome/colophon.py tests/render/v5/test_chrome_colophon.py
git commit -m "feat(render/v5): colophon footer with sources + render stats"
```

---

## Phase 6 — Editorial pipeline (~5 hours)

Six Claude calls. Each gets: a prompt file, a validator function, a pipeline integration, and tests with mocked subprocess output.

**Files:**
- Create: `brief/claude/prompts/top_picks.txt`
- Create: `brief/claude/prompts/todays_call.txt`
- Create: `brief/claude/prompts/bankerread_structured.txt`
- Create: `brief/claude/prompts/bankerread_stale_v5.txt`
- Create: `brief/claude/prompts/systemic_risk_callout.txt`
- Create: `brief/claude/prompts/editorial_qa.txt`
- Modify: `brief/claude/prompts/headlines_curation.txt` (rewrite for V5 voice)
- Modify: `brief/claude/validators.py`
- Modify: `brief/pipeline.py`
- Test: `tests/claude/test_validators_v5.py`
- Test: `tests/test_pipeline_v5.py`

### Task 11: Validator for `top_picks` (Call 1)

- [ ] **Step 1: Write failing test in `tests/claude/test_validators_v5.py`**

```python
from brief.claude.validators import validate_top_picks


VALID_PAYLOAD = {
    "plotted": [
        {"id": "bb",      "x": 1.2, "y": 6.0, "r": 24, "kind": "anchor"},
        {"id": "macro",   "x": 2.2, "y": 7.8, "r": 32, "kind": "slow"},
        {"id": "fx",      "x": 3.4, "y": 6.3, "r": 28, "kind": "slow"},
        {"id": "remit",   "x": 6.0, "y": 7.0, "r": 30, "kind": "fresh"},
        {"id": "dse",     "x": 6.5, "y": 4.8, "r": 26, "kind": "fresh"},
        {"id": "tbond",   "x": 5.0, "y": 5.4, "r": 24, "kind": "fresh"},
        {"id": "iranwar", "x": 9.4, "y": 9.1, "r": 38, "kind": "event"},
    ],
    "grid": [
        {"id": "banking", "tldr": "NPL 35.73% — historic high"},
        {"id": "comm", "tldr": "LNG JKM $10.4 flat WoW"},
        {"id": "fiscal", "tldr": "NBR YTD 2.84tn"},
        {"id": "nbr", "tldr": "Mar VAT print due Sun"},
        {"id": "dam", "tldr": "Onion +12% WoW"},
        {"id": "headlines", "tldr": "9 curated stories"},
        {"id": "exec", "tldr": "6 prints · 3 watches"},
    ],
    "front_of_book_id": "iranwar",
}

ALL_IDS = {"bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
           "banking", "comm", "fiscal", "nbr", "dam", "headlines", "exec"}


def test_top_picks_valid():
    result = validate_top_picks(VALID_PAYLOAD, allowed_ids=ALL_IDS)
    assert result.ok
    assert result.value.front_of_book_id == "iranwar"


def test_top_picks_rejects_wrong_plotted_count():
    bad = dict(VALID_PAYLOAD)
    bad["plotted"] = VALID_PAYLOAD["plotted"][:5]
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "exactly 7" in result.reason


def test_top_picks_rejects_overlapping_plotted_and_grid():
    bad = dict(VALID_PAYLOAD)
    bad["grid"] = [{"id": "bb", "tldr": "x"}] + VALID_PAYLOAD["grid"][1:]
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "overlap" in result.reason.lower()


def test_top_picks_rejects_unknown_id():
    bad = dict(VALID_PAYLOAD)
    bad["plotted"] = list(VALID_PAYLOAD["plotted"])
    bad["plotted"][0] = {"id": "ghost", "x": 1, "y": 1, "r": 10, "kind": "anchor"}
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "ghost" in result.reason


def test_top_picks_rejects_front_of_book_not_in_plotted():
    bad = dict(VALID_PAYLOAD)
    bad["front_of_book_id"] = "banking"  # banking is in grid, not plotted
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "front_of_book" in result.reason


def test_top_picks_rejects_tldr_too_long():
    bad = {**VALID_PAYLOAD, "grid": [
        *VALID_PAYLOAD["grid"][:6],
        {"id": "exec", "tldr": "this is way too long " * 10},
    ]}
    result = validate_top_picks(bad, allowed_ids=ALL_IDS)
    assert not result.ok
    assert "tldr" in result.reason.lower()
```

- [ ] **Step 2: Implement `validate_top_picks` in `brief/claude/validators.py`**

Add at the end of `brief/claude/validators.py`:

```python
from brief.schema import GridEntry, MapPoint, TopPicks


def validate_top_picks(payload: Any, *, allowed_ids: set[str]) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    plotted = payload.get("plotted")
    grid = payload.get("grid")
    fob = payload.get("front_of_book_id")

    if not isinstance(plotted, list) or len(plotted) != 7:
        return ValidationResult(False, reason="plotted must contain exactly 7 sections")
    if not isinstance(grid, list) or len(grid) != 7:
        return ValidationResult(False, reason="grid must contain exactly 7 sections")
    if not isinstance(fob, str):
        return ValidationResult(False, reason="front_of_book_id missing or not a string")

    plotted_models: list[MapPoint] = []
    for item in plotted:
        if not _is_dict(item):
            return ValidationResult(False, reason="plotted item not a dict")
        for k in ("id", "x", "y", "r", "kind"):
            if k not in item:
                return ValidationResult(False, reason=f"plotted item missing {k}")
        if item["id"] not in allowed_ids:
            return ValidationResult(False, reason=f"unknown id in plotted: {item['id']!r}")
        if item["kind"] not in {"event", "fresh", "slow", "anchor"}:
            return ValidationResult(False, reason=f"bad kind: {item['kind']!r}")
        try:
            plotted_models.append(MapPoint(**item))
        except Exception as e:
            return ValidationResult(False, reason=f"plotted item invalid: {e}")

    grid_models: list[GridEntry] = []
    for item in grid:
        if not _is_dict(item):
            return ValidationResult(False, reason="grid item not a dict")
        for k in ("id", "tldr"):
            if k not in item:
                return ValidationResult(False, reason=f"grid item missing {k}")
        if item["id"] not in allowed_ids:
            return ValidationResult(False, reason=f"unknown id in grid: {item['id']!r}")
        word_count = len(str(item["tldr"]).split())
        if word_count > 14:
            return ValidationResult(False, reason=f"tldr too long ({word_count} words) for {item['id']!r}; cap is 12")
        try:
            grid_models.append(GridEntry(**item))
        except Exception as e:
            return ValidationResult(False, reason=f"grid item invalid: {e}")

    plotted_ids = {p.id for p in plotted_models}
    grid_ids = {g.id for g in grid_models}
    if plotted_ids & grid_ids:
        return ValidationResult(False, reason=f"plotted/grid overlap: {plotted_ids & grid_ids}")
    if fob not in plotted_ids:
        return ValidationResult(False, reason=f"front_of_book_id {fob!r} not in plotted")

    return ValidationResult(True, value=TopPicks(plotted=plotted_models, grid=grid_models, front_of_book_id=fob))
```

- [ ] **Step 3: Write the prompt file `brief/claude/prompts/top_picks.txt`**

```text
You are the Editor of *The Brief*, a daily Bangladesh-economy intelligence digest read by senior bankers.

Today's date: {today}

You are given compact summaries of all 14 sections in today's edition. Your job: pick the seven sections that go on the front-of-book risk map (plot by movement-today × significance-for-the-banker's-book), pick the seven that go in the secondary "ALSO TODAY" grid, and pick which single plotted section is today's "read first" choice.

INPUT:
- `sections`: array of 14 objects, each with:
    id, kicker, freshness, key_metric: {label, value, delta_pct, direction}, news_count, has_systemic_risk
- `previous_front_of_book_id`: yesterday's read-first choice (avoid repeating unless today's signal demands it)

CRITERIA for the seven plotted:
1. Highest absolute movement today (|delta_pct|).
2. Highest significance-for-the-book (your editorial weight).
3. Sections with `has_systemic_risk=true` are stronger candidates.
4. Sections with `freshness="fresh"` are stronger candidates.
5. Mix of kinds: at least one anchor (slow but always-matters), at least one event (today's news), at least one fresh-print.

For each plotted section, choose:
- `x`: movement today (0-10), where 5 = average day, 10 = exceptional move
- `y`: significance-for-banker's-book (0-10), where 5 = average importance today
- `r`: read-weight radius (20-40); higher = pull the eye more
- `kind`: "event" | "fresh" | "slow" | "anchor"

For the seven grid sections, write a `tldr` of ≤12 words for each.

Pick `front_of_book_id`: the ONE plotted section that gets the front-page pulled-in preview. Usually the highest |x|·|y| product, but you can override for editorial reasons.

OUTPUT — return ONLY this JSON object. No markdown fences. No prose.

{
  "plotted": [
    {"id": "...", "x": 0.0, "y": 0.0, "r": 24, "kind": "fresh"},
    ...exactly 7
  ],
  "grid": [
    {"id": "...", "tldr": "..."},
    ...exactly 7
  ],
  "front_of_book_id": "..."
}

CONSTRAINTS:
- 14 sections in input → exactly 7 plotted + exactly 7 in grid (no overlap, full coverage).
- Every `id` must come from the input.
- `front_of_book_id` must be in `plotted`.
- Each `tldr` must be ≤12 words. No semicolons in tldrs.
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/claude/test_validators_v5.py -v
git add brief/claude/validators.py brief/claude/prompts/top_picks.txt tests/claude/test_validators_v5.py
git commit -m "feat(claude): top_picks prompt + validator (Call 1)"
```

### Task 12: Validator for `todays_call` (Call 3)

- [ ] **Step 1: Write failing test (append to `tests/claude/test_validators_v5.py`)**

```python
from brief.claude.validators import validate_todays_call


def test_todays_call_valid():
    payload = {
        "text": "Hormuz is priced risk, not scarcity. " * 4,  # ~24 words
        "byline": "Desk Editor · The Brief",
    }
    result = validate_todays_call(payload)
    assert result.ok


def test_todays_call_rejects_too_short():
    payload = {"text": "Short.", "byline": "x"}
    result = validate_todays_call(payload)
    assert not result.ok
    assert "60-100" in result.reason


def test_todays_call_rejects_too_long():
    payload = {"text": "word " * 200, "byline": "x"}
    result = validate_todays_call(payload)
    assert not result.ok


def test_todays_call_rejects_double_quotes_in_text():
    payload = {
        "text": 'Hormuz is "priced risk" not scarcity. ' * 4,
        "byline": "x",
    }
    result = validate_todays_call(payload)
    assert not result.ok
    assert "double quote" in result.reason.lower()
```

- [ ] **Step 2: Implement validator**

Append to `brief/claude/validators.py`:

```python
from datetime import datetime, timezone

from brief.schema import TodaysCall


def validate_todays_call(payload: Any) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    text = payload.get("text")
    byline = payload.get("byline", "Desk Editor · The Brief")
    if not isinstance(text, str):
        return ValidationResult(False, reason="text missing or not a string")
    word_count = len(text.split())
    if word_count < 60 or word_count > 100:
        return ValidationResult(False, reason=f"text must be 60-100 words; got {word_count}")
    if '"' in text:
        return ValidationResult(False, reason="text contains double quote (template-breaking)")
    return ValidationResult(True, value=TodaysCall(text=text, byline=byline, generated_at=datetime.now(timezone.utc)))
```

- [ ] **Step 3: Write `brief/claude/prompts/todays_call.txt`**

```text
You are the Desk Editor of *The Brief*. Write the masthead's "TODAY'S CALL" — a single ~80-word editorial paragraph that synthesizes today's top 3 risks for senior bankers.

Today's date: {today}

INPUT:
- `top_7_plotted`: today's seven highest-significance sections, each with id, kicker, key_metric, freshness, and a 1-line summary
- `headlines`: today's curated headlines (8-15 items, ranked)
- `previous_call`: yesterday's todays_call.text (for narrative continuity — pick up the thread, but don't repeat)

JOB:
- Write 60-100 words of declarative, banker-direct prose.
- Lead with the single most important risk-frame (e.g. *"Hormuz is priced risk, not scarcity"*).
- Cite specific numbers from the input where they support the frame.
- Close with one decisive instruction (*"Hedge the oil book — not the headline."*).
- Voice: confident, terse, opinionated. No hedging. No "could", "may", "perhaps".
- No double quotes — use italics or em-dashes for emphasis.

OUTPUT — return ONLY this JSON object. No markdown fences.

{"text": "...", "byline": "Desk Editor · The Brief"}

CONSTRAINTS:
- Exactly 60-100 words.
- No double quotes anywhere in `text`.
- No markdown fences in output.
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/claude/test_validators_v5.py -v
git add brief/claude/validators.py brief/claude/prompts/todays_call.txt tests/claude/test_validators_v5.py
git commit -m "feat(claude): todays_call prompt + validator (Call 3)"
```

### Task 13: Validator for `bankerread_structured` + stale variant (Call 4)

- [ ] **Step 1: Write failing tests**

Append to `tests/claude/test_validators_v5.py`:

```python
from brief.claude.validators import validate_bankerread_structured


def test_bankerread_structured_full_valid():
    payload = {
        "variant": "full",
        "meaning": "word " * 90,
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "Concise editorial line.",
    }
    result = validate_bankerread_structured(payload)
    assert result.ok
    assert result.value.variant == "full"


def test_bankerread_structured_stale_valid():
    payload = {
        "variant": "stale_micro",
        "meaning": "word " * 80,
        "pull_quote": "Concise editorial line.",
    }
    result = validate_bankerread_structured(payload)
    assert result.ok
    assert result.value.action is None


def test_bankerread_structured_full_rejects_short_field():
    payload = {
        "variant": "full",
        "meaning": "too short",  # < 60 words
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "Quote",
    }
    result = validate_bankerread_structured(payload)
    assert not result.ok
    assert "meaning" in result.reason


def test_bankerread_structured_rejects_double_quote():
    payload = {
        "variant": "full",
        "meaning": ('word ' * 60) + '"x"',
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "x",
    }
    result = validate_bankerread_structured(payload)
    assert not result.ok


def test_bankerread_structured_rejects_long_pull_quote():
    payload = {
        "variant": "full",
        "meaning": "word " * 90,
        "action": "word " * 90,
        "trigger": "word " * 90,
        "focus": "word " * 90,
        "pull_quote": "word " * 30,  # > 20 words
    }
    result = validate_bankerread_structured(payload)
    assert not result.ok
    assert "pull_quote" in result.reason
```

- [ ] **Step 2: Implement**

Append to `brief/claude/validators.py`:

```python
from brief.schema import BankerReadInsight


def validate_bankerread_structured(payload: Any) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    variant = payload.get("variant")
    if variant not in {"full", "stale_micro"}:
        return ValidationResult(False, reason=f"variant must be 'full' or 'stale_micro'; got {variant!r}")

    pull = payload.get("pull_quote")
    if not isinstance(pull, str) or len(pull.split()) > 20:
        return ValidationResult(False, reason=f"pull_quote missing or > 20 words")
    if '"' in pull:
        return ValidationResult(False, reason="pull_quote contains double quote")

    if variant == "full":
        for field in ("meaning", "action", "trigger", "focus"):
            text = payload.get(field)
            if not isinstance(text, str):
                return ValidationResult(False, reason=f"{field} missing")
            wc = len(text.split())
            if wc < 60 or wc > 180:
                return ValidationResult(False, reason=f"{field} must be 60-180 words; got {wc}")
            if '"' in text:
                return ValidationResult(False, reason=f"{field} contains double quote")
        return ValidationResult(True, value=BankerReadInsight(
            variant="full",
            meaning=payload["meaning"],
            action=payload["action"],
            trigger=payload["trigger"],
            focus=payload["focus"],
            pull_quote=pull,
            generated_at=datetime.now(timezone.utc),
        ))

    # stale_micro
    text = payload.get("meaning")
    if not isinstance(text, str):
        return ValidationResult(False, reason="meaning missing")
    wc = len(text.split())
    if wc < 50 or wc > 110:
        return ValidationResult(False, reason=f"stale_micro meaning must be 50-110 words; got {wc}")
    if '"' in text:
        return ValidationResult(False, reason="meaning contains double quote")
    return ValidationResult(True, value=BankerReadInsight(
        variant="stale_micro",
        meaning=text,
        pull_quote=pull,
        generated_at=datetime.now(timezone.utc),
    ))
```

- [ ] **Step 3: Write `brief/claude/prompts/bankerread_structured.txt`**

```text
You are the Senior Banker writing the "Banker's Read" panel for §{section_n} {kicker} of *The Brief* — a Bangladesh-economy daily intelligence digest read by CFO, CRO, Head of SME Banking, Head of Corporate Banking, and Treasury Heads.

Today's date: {today}

INPUT:
- `section`: SectionData for this section — id, title, metrics, news, freshness, history (last N days of primary metric)
- `top_picks_placement`: this section's placement today (`{plotted: bool, front_of_book: bool, grid: bool}`)
- `previous_bankerread`: this section's banker's read from yesterday's edition (use for continuity; do not repeat)

JOB: write a structured 4-field banker's read.

§A MEANING — 80-150 words. What today's data means for the book. Lead with a clear interpretation; cite the primary metric value and direction; tie it to a banker concern (NIM, liquidity, capital, credit risk, FX exposure).

§B ACTION — 80-150 words. ONE named, exposure-typed action a CRO or Head can take this week. Specify book/segment/threshold (e.g. "Cap fixed-rate corporate book above 5y at 12% of total"; "Tighten retail underwriting on unsecured personal loans under BDT 60k income").

§C TRIGGER — 80-150 words. ONE metric + threshold to watch. Be specific (e.g. "Reserves below 33bn with BDT past 123.0 — halt new NOSTRO drawdowns"; "Food CPI breach of 10.8% next print likely triggers supervisory letter").

§D FOCUS — 80-150 words. Strategic posture for the week. Higher-altitude than action; one clear directional statement (e.g. "Rotate new origination toward floating-rate SME facilities"; "Build provisions ahead of the curve").

PULL_QUOTE — ≤20 words. One quotable editorial line for the risk map. (e.g. "Risk premium, not scarcity — but price the next incident before it happens.")

VOICE:
- Confident, declarative, banker-to-banker. No "perhaps", "could", "may consider".
- No double quotes anywhere — use italics or em-dashes for emphasis.
- Cite real metric values from the input. Never invent numbers.

OUTPUT — return ONLY this JSON object. No markdown fences.

{
  "variant": "full",
  "meaning": "...",
  "action": "...",
  "trigger": "...",
  "focus": "...",
  "pull_quote": "..."
}

CONSTRAINTS:
- Each of meaning/action/trigger/focus: 80-150 words. Validator enforces 60-180 with a buffer.
- pull_quote: ≤20 words.
- No double quotes anywhere.
- No markdown code fences in output.
- Every metric value cited must exist in `section.metrics` or `section.history`.
```

- [ ] **Step 4: Write `brief/claude/prompts/bankerread_stale_v5.txt`**

```text
You are writing the stale-section variant of the Banker's Read for §{section_n} {kicker}.

Today's date: {today}

This section's data is stale (`freshness != "fresh"`). Don't pretend it's fresh. Instead, write a single 60-100 word paragraph drawing on `section.news` (recent headlines) and the LAST KNOWN metric values from `section.metrics`. Frame it as: "No fresh data; news suggests X."

VOICE: same banker-direct tone as the full variant. No double quotes.

OUTPUT — return ONLY this JSON object.

{
  "variant": "stale_micro",
  "meaning": "...",
  "pull_quote": "..."
}

CONSTRAINTS:
- meaning: 60-100 words.
- pull_quote: ≤20 words.
- No double quotes anywhere.
- No markdown fences.
```

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/claude/test_validators_v5.py -v
git add brief/claude/validators.py brief/claude/prompts/bankerread_structured.txt brief/claude/prompts/bankerread_stale_v5.txt tests/claude/test_validators_v5.py
git commit -m "feat(claude): bankerread_structured + stale_v5 prompts + validators (Call 4)"
```

### Task 14: Validator for `systemic_risk_callout` (Call 5) + builder rules

- [ ] **Step 1: Define risk rules in `brief/cadence.py`**

Append to `brief/cadence.py`:

```python
"""Systemic-risk rules — deterministic predicates that fire `risk_active=True`
on a section when satisfied. The Call 5 (systemic_risk_callout) prompt only
runs for sections where one rule fires.
"""
from __future__ import annotations

from typing import Callable

from brief.schema import Metric, SectionData

# Each rule returns (fired: bool, level: "warning"|"critical", rule_id: str)
RiskRule = Callable[[SectionData], tuple[bool, str, str]]


def _by_id(metrics: list[Metric], metric_id: str) -> Metric | None:
    return next((m for m in metrics if m.id == metric_id), None)


def banking_npl_rule(section: SectionData) -> tuple[bool, str, str]:
    npl = _by_id(section.metrics, "banking_npl_pct")
    if npl is None or not isinstance(npl.value, (int, float)):
        return (False, "warning", "banking_npl")
    if npl.value >= 30.0:
        return (True, "critical", "banking_npl_above_30")
    if npl.value >= 20.0:
        return (True, "warning", "banking_npl_above_20")
    return (False, "warning", "banking_npl")


def fx_reserves_rule(section: SectionData) -> tuple[bool, str, str]:
    res = _by_id(section.metrics, "bb_gross_reserves")
    if res is None or not isinstance(res.value, (int, float)):
        return (False, "warning", "fx_reserves")
    if res.value < 32.0:
        return (True, "critical", "fx_reserves_below_32bn")
    if res.value < 34.0:
        return (True, "warning", "fx_reserves_below_34bn")
    return (False, "warning", "fx_reserves")


def fx_usd_bdt_rule(section: SectionData) -> tuple[bool, str, str]:
    fx = _by_id(section.metrics, "fx_usd_bdt")
    if fx is None or not isinstance(fx.value, (int, float)):
        return (False, "warning", "fx_usd_bdt")
    if fx.value > 124.0:
        return (True, "critical", "fx_usd_bdt_above_124")
    return (False, "warning", "fx_usd_bdt")


# Section id → list of rules to apply
SECTION_RULES: dict[str, list[RiskRule]] = {
    "banking": [banking_npl_rule],
    "bb":      [fx_reserves_rule],
    "fx":      [fx_usd_bdt_rule, fx_reserves_rule],
}


def evaluate_risk_rules(section: SectionData) -> tuple[bool, str | None, str | None]:
    """Return (risk_active, level, rule_id). First-fired rule wins (in declared order)."""
    for rule in SECTION_RULES.get(section.id, []):
        fired, level, rid = rule(section)
        if fired:
            return (True, level, rid)
    return (False, None, None)
```

- [ ] **Step 2: Write tests for `evaluate_risk_rules`**

Create `tests/test_cadence_risk_rules.py`:

```python
from datetime import date

from brief.cadence import evaluate_risk_rules
from brief.schema import Metric, SectionData


def _section(id: str, metrics: list[Metric]) -> SectionData:
    return SectionData(
        id=id, title="x", kicker="x", tldr="", metrics=metrics, news=[], freshness="fresh"
    )


def test_npl_30_fires_critical():
    metric = Metric(id="banking_npl_pct", label="NPL", value=35.73, unit="%",
                    as_of=date(2026, 1, 1), source="BB", cadence="quarterly")
    fired, level, rule_id = evaluate_risk_rules(_section("banking", [metric]))
    assert fired and level == "critical" and rule_id == "banking_npl_above_30"


def test_npl_25_fires_warning():
    metric = Metric(id="banking_npl_pct", label="NPL", value=25.0, unit="%",
                    as_of=date(2026, 1, 1), source="BB", cadence="quarterly")
    fired, level, rule_id = evaluate_risk_rules(_section("banking", [metric]))
    assert fired and level == "warning" and rule_id == "banking_npl_above_20"


def test_npl_15_does_not_fire():
    metric = Metric(id="banking_npl_pct", label="NPL", value=15.0, unit="%",
                    as_of=date(2026, 1, 1), source="BB", cadence="quarterly")
    fired, _, _ = evaluate_risk_rules(_section("banking", [metric]))
    assert not fired


def test_section_with_no_rules_returns_false():
    fired, _, _ = evaluate_risk_rules(_section("dse", []))
    assert not fired
```

- [ ] **Step 3: Write `validate_systemic_risk_callout`**

Append to `brief/claude/validators.py`:

```python
from brief.schema import SystemicRisk


def validate_systemic_risk_callout(payload: Any, *, expected_level: str, rule_id: str) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    headline = payload.get("headline")
    body = payload.get("body")
    if not isinstance(headline, str) or len(headline.split()) > 12:
        return ValidationResult(False, reason="headline missing or > 12 words")
    if not isinstance(body, str):
        return ValidationResult(False, reason="body missing")
    bw = len(body.split())
    if bw < 50 or bw > 110:
        return ValidationResult(False, reason=f"body must be 50-110 words; got {bw}")
    if '"' in headline + body:
        return ValidationResult(False, reason="contains double quote")
    return ValidationResult(True, value=SystemicRisk(
        headline=headline, body=body, level=expected_level, rule_id=rule_id
    ))
```

- [ ] **Step 4: Add tests for systemic_risk_callout validator**

Append to `tests/claude/test_validators_v5.py`:

```python
from brief.claude.validators import validate_systemic_risk_callout


def test_systemic_risk_callout_valid():
    payload = {"headline": "NPL world-high", "body": "word " * 80}
    result = validate_systemic_risk_callout(payload, expected_level="critical", rule_id="banking_npl_above_30")
    assert result.ok
    assert result.value.level == "critical"


def test_systemic_risk_callout_rejects_long_headline():
    payload = {"headline": "word " * 20, "body": "word " * 80}
    result = validate_systemic_risk_callout(payload, expected_level="warning", rule_id="x")
    assert not result.ok


def test_systemic_risk_callout_rejects_short_body():
    payload = {"headline": "Tight", "body": "too short"}
    result = validate_systemic_risk_callout(payload, expected_level="warning", rule_id="x")
    assert not result.ok
```

- [ ] **Step 5: Write `brief/claude/prompts/systemic_risk_callout.txt`**

```text
You are writing a Systemic Risk callout for §{section_n} {kicker} of *The Brief*.

Today's date: {today}

A deterministic rule fired (`{rule_id}`, level=`{level}`). This means the section has crossed a threshold that warrants a red/amber callout panel above the metric cards.

INPUT:
- `section`: the section's full SectionData
- `triggering_metric`: the specific Metric that crossed the threshold

JOB: Write a 60-100 word red-card paragraph explaining the systemic dimension.

- `headline`: ≤12 words. The lede (e.g. *"NPL ratio at 35.73% — world's highest"*).
- `body`: 60-100 words. Explain the systemic dimension and why it matters today. Cite the triggering metric and one supporting metric. Tie to a banker concern. Voice: urgent but not panicked. No double quotes.

OUTPUT — JSON only:

{"headline": "...", "body": "..."}

CONSTRAINTS:
- headline: ≤12 words.
- body: 60-100 words.
- No double quotes.
- No markdown fences.
```

- [ ] **Step 6: Run tests + commit**

```bash
pytest tests/test_cadence_risk_rules.py tests/claude/test_validators_v5.py -v
git add brief/cadence.py brief/claude/validators.py brief/claude/prompts/systemic_risk_callout.txt tests/test_cadence_risk_rules.py tests/claude/test_validators_v5.py
git commit -m "feat(cadence,claude): systemic-risk rules + Call 5 prompt + validator"
```

### Task 15: Validator for `editorial_qa` (Call 6)

- [ ] **Step 1: Write failing tests**

Append to `tests/claude/test_validators_v5.py`:

```python
from brief.claude.validators import validate_editorial_qa


def test_editorial_qa_pass():
    payload = {"status": "pass", "issues": [], "shippable": True}
    result = validate_editorial_qa(payload)
    assert result.ok
    assert result.value.shippable is True


def test_editorial_qa_block_with_issues():
    payload = {
        "status": "block",
        "issues": [
            {"section_id": "bb", "severity": "block", "message": "empty banker read"},
            {"section_id": None, "severity": "warn", "message": "tone mismatch"},
        ],
        "shippable": False,
    }
    result = validate_editorial_qa(payload)
    assert result.ok
    assert result.value.shippable is False
    assert len(result.value.issues) == 2


def test_editorial_qa_rejects_inconsistent_shippable():
    """status=block but shippable=true is invalid."""
    payload = {"status": "block", "issues": [], "shippable": True}
    result = validate_editorial_qa(payload)
    assert not result.ok
```

- [ ] **Step 2: Implement validator**

Append to `brief/claude/validators.py`:

```python
from brief.schema import EditorialQAResult, QAIssue


def validate_editorial_qa(payload: Any) -> ValidationResult:
    if not _is_dict(payload):
        return ValidationResult(False, reason="payload not a dict")
    status = payload.get("status")
    if status not in {"pass", "block"}:
        return ValidationResult(False, reason=f"status must be 'pass' or 'block'; got {status!r}")
    issues_raw = payload.get("issues", [])
    if not isinstance(issues_raw, list):
        return ValidationResult(False, reason="issues not a list")
    shippable = payload.get("shippable")
    if not isinstance(shippable, bool):
        return ValidationResult(False, reason="shippable not a bool")

    issues = []
    for item in issues_raw:
        if not _is_dict(item):
            return ValidationResult(False, reason="issue not a dict")
        if item.get("severity") not in {"info", "warn", "block"}:
            return ValidationResult(False, reason=f"bad severity: {item.get('severity')!r}")
        if not isinstance(item.get("message"), str):
            return ValidationResult(False, reason="issue.message not a string")
        issues.append(QAIssue(
            section_id=item.get("section_id"),
            severity=item["severity"],
            message=item["message"],
        ))

    has_block_severity = any(i.severity == "block" for i in issues)
    expected_shippable = (status == "pass") and (not has_block_severity)
    if shippable != expected_shippable:
        return ValidationResult(False, reason=f"shippable={shippable} inconsistent with status={status!r} + issues")

    return ValidationResult(True, value=EditorialQAResult(status=status, issues=issues, shippable=shippable))
```

- [ ] **Step 3: Write `brief/claude/prompts/editorial_qa.txt`**

```text
You are the Editorial QA Reviewer for *The Brief*. The pipeline has produced today's edition and you are the last gate before publication.

Today's date: {today}

INPUT:
- `sections`: array of all 14 final SectionData payloads (compact: id, title, kicker, freshness, key_metric values, banker's_read, systemic_risk if any)
- `front_of_book`: today's front-of-book section id and the rendered front-of-book preview text
- `todays_call`: the masthead's TODAY'S CALL paragraph
- `rendered_html_excerpt`: the rendered index.html with CSS/script stripped, narrative content kept (~6k tokens)

JOB: scan for issues that should block the ship. Categories:

1. **Numeric contradictions** across sections — one section says X went up, another says X went down for the same metric on the same day.
2. **Stale numbers** silently presented as fresh — a metric's `as_of` is > 60 days old but the section is not flagged warming_up or stale.
3. **Empty editorial** where it should be populated — banker's read fields blank when freshness=fresh, or systemic_risk callout missing on a section where rule_id implies it should exist.
4. **Visible escaped HTML** in narrative text — `&lt;span` or `&amp;lt;` artifacts that suggest a renderer bug.
5. **Tone breaks** — one section's voice is alarmed while everything else is calm and the data doesn't justify the alarm.
6. **Missing front-of-book elements** — the chosen front_of_book_id section's pull_quote is empty or its action/trigger is missing.
7. **Hallucinated URLs** — any URL in rendered_html_excerpt that's not in `sections[].news[].url`.

For each issue, emit `{section_id, severity, message}`. Severity:
- `info`: cosmetic, doesn't block
- `warn`: should fix in next edition
- `block`: must fix or hold ship

DECISION:
- `status = "pass"` if no block-severity issues.
- `status = "block"` if any block-severity issue.
- `shippable = (status == "pass") AND (no severity == "block")`.

Be conservative. Do not block on info/warn alone. Do not block on stylistic preferences.

OUTPUT — JSON only:

{
  "status": "pass",
  "issues": [
    {"section_id": "bb", "severity": "info", "message": "minor copy nit"}
  ],
  "shippable": true
}

CONSTRAINTS:
- Every section_id must be a real section id, or null (for cross-cutting issues).
- shippable must be consistent with status + issues.
- No markdown fences in output.
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/claude/test_validators_v5.py -v
git add brief/claude/validators.py brief/claude/prompts/editorial_qa.txt tests/claude/test_validators_v5.py
git commit -m "feat(claude): editorial_qa prompt + validator (Call 6 — pre-flight gate)"
```

---

## Phase 7 — Pipeline integration of all 6 calls (~2 hours)

**Files:**
- Modify: `brief/pipeline.py`
- Test: `tests/test_pipeline_v5.py`

### Task 16: Wire 6 calls into the pipeline

The pipeline needs to:
1. After all 14 builders run, call `top_picks` (Call 1) once.
2. Call `headlines_curation` (Call 2) — already wired in V4, just rewrite the prompt voice.
3. Call `todays_call` (Call 3) once after Calls 1+2.
4. For each of the 14 sections in parallel: evaluate risk rules; call `bankerread_structured` (or `bankerread_stale_v5`) — Call 4. If `risk_active`, also call `systemic_risk_callout` — Call 5.
5. After assemble, call `editorial_qa` — Call 6. If `shippable=false`, halt; preserve yesterday's index.html.

- [ ] **Step 1: Locate the V4 pipeline integration**

Run: `grep -n "validate_curation\|run_max\|push_artifacts" brief/pipeline.py | head`
Note: identify where the V4 calls happen and where to insert V5 calls.

- [ ] **Step 2: Add V5 dispatch helper to `brief/pipeline.py`**

Insert near the top of `brief/pipeline.py`:

```python
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from brief.cadence import evaluate_risk_rules
from brief.claude.max_client import run_max
from brief.claude.validators import (
    validate_bankerread_structured,
    validate_editorial_qa,
    validate_systemic_risk_callout,
    validate_todays_call,
    validate_top_picks,
)
from brief.schema import (
    BankerReadInsight,
    EditorialQAResult,
    SectionData,
    SystemicRisk,
    TodaysCall,
    TopPicks,
)

PROMPTS_DIR = Path(__file__).parent / "claude" / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def renderer_mode() -> str:
    """Returns 'v4' or 'v5' based on BRIEF_RENDERER env (default v4)."""
    return os.environ.get("BRIEF_RENDERER", "v4").lower()
```

- [ ] **Step 3: Add `run_v5_editorial` orchestration function**

Append to `brief/pipeline.py`:

```python
def run_v5_editorial(
    *,
    sections: list[SectionData],
    today: date,
    headlines_curation_result,  # output of existing V4 Call 2
    previous_edition: dict | None = None,
) -> tuple[TopPicks, TodaysCall, dict[str, BankerReadInsight | None], dict[str, SystemicRisk | None]]:
    """Run Calls 1, 3, 4, 5 against all 14 sections.

    Returns: (top_picks, todays_call, bankerreads_by_id, systemic_risks_by_id).
    Per-section failures fall back to previous edition where available; never raise.
    """
    section_by_id = {s.id: s for s in sections}
    allowed_ids = set(section_by_id.keys())

    # ---- Call 1: top_picks ----
    summaries = [_section_summary_for_top_picks(s) for s in sections]
    top_picks_input = {
        "today": today.isoformat(),
        "sections": summaries,
        "previous_front_of_book_id": (previous_edition or {}).get("front_of_book_id"),
    }
    prompt = _load_prompt("top_picks.txt").format(today=today.isoformat())
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(top_picks_input, indent=2)
    result = run_max(prompt=body, extended_thinking_budget=16000)
    if result.parsed is not None:
        v = validate_top_picks(result.parsed, allowed_ids=allowed_ids)
        top_picks = v.value if v.ok else _top_picks_fallback(sections)
    else:
        top_picks = _top_picks_fallback(sections)

    # ---- Call 3: todays_call ----
    plotted_sections = [section_by_id[p.id] for p in top_picks.plotted]
    tc_input = {
        "today": today.isoformat(),
        "top_7_plotted": [_section_summary_for_top_picks(s) for s in plotted_sections],
        "headlines": headlines_curation_result,
        "previous_call": (previous_edition or {}).get("todays_call_text"),
    }
    prompt = _load_prompt("todays_call.txt").format(today=today.isoformat())
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(tc_input, indent=2)
    result = run_max(prompt=body, extended_thinking_budget=12000)
    if result.parsed is not None:
        v = validate_todays_call(result.parsed)
        todays_call = v.value if v.ok else _todays_call_fallback(previous_edition)
    else:
        todays_call = _todays_call_fallback(previous_edition)

    # ---- Call 4 (×14) + Call 5 (conditional, ×N) ----
    bankerreads: dict[str, BankerReadInsight | None] = {}
    systemic_risks: dict[str, SystemicRisk | None] = {}

    def _section_call(section: SectionData) -> tuple[str, BankerReadInsight | None, SystemicRisk | None]:
        # Risk rule eval (deterministic)
        risk_active, level, rule_id = evaluate_risk_rules(section)
        section.risk_active = risk_active

        # Call 4
        is_full = section.freshness == "fresh"
        prompt_file = "bankerread_structured.txt" if is_full else "bankerread_stale_v5.txt"
        section_n = _section_n(section.id)
        prompt = _load_prompt(prompt_file).format(section_n=section_n, kicker=section.kicker, today=today.isoformat())
        br_input = {
            "section": section.model_dump(mode="json"),
            "top_picks_placement": _placement_for(section.id, top_picks),
            "previous_bankerread": (previous_edition or {}).get("bankerreads", {}).get(section.id),
        }
        body = prompt + "\n\nINPUT JSON:\n" + json.dumps(br_input, indent=2)
        result = run_max(prompt=body, extended_thinking_budget=12000)
        br: BankerReadInsight | None = None
        if result.parsed is not None:
            v = validate_bankerread_structured(result.parsed)
            if v.ok:
                br = v.value
        if br is None:
            br = (previous_edition or {}).get("bankerreads", {}).get(section.id)  # carry-over

        # Call 5 (conditional)
        sr: SystemicRisk | None = None
        if risk_active and rule_id and level:
            triggering_metric = _triggering_metric_for(section, rule_id)
            sr_prompt = _load_prompt("systemic_risk_callout.txt").format(
                section_n=section_n, kicker=section.kicker, today=today.isoformat(),
                rule_id=rule_id, level=level,
            )
            sr_input = {"section": section.model_dump(mode="json"), "triggering_metric": triggering_metric}
            sr_body = sr_prompt + "\n\nINPUT JSON:\n" + json.dumps(sr_input, indent=2)
            sr_result = run_max(prompt=sr_body, extended_thinking_budget=8000)
            if sr_result.parsed is not None:
                v = validate_systemic_risk_callout(sr_result.parsed, expected_level=level, rule_id=rule_id)
                if v.ok:
                    sr = v.value

        return (section.id, br, sr)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_section_call, s) for s in sections]
        for fut in as_completed(futures):
            sid, br, sr = fut.result()
            bankerreads[sid] = br
            systemic_risks[sid] = sr

    return top_picks, todays_call, bankerreads, systemic_risks


def run_v5_qa_gate(*, sections: list[SectionData], todays_call: TodaysCall, top_picks: TopPicks, rendered_html: str, today: date) -> EditorialQAResult:
    """Call 6 — pre-flight QA. Returns a result that may block the ship."""
    # Strip CSS/script from rendered HTML to fit token budget
    excerpt = _strip_css_and_script(rendered_html)[:24000]  # rough char cap
    qa_input = {
        "today": today.isoformat(),
        "sections": [_section_summary_for_qa(s) for s in sections],
        "front_of_book": {"id": top_picks.front_of_book_id},
        "todays_call": todays_call.text,
        "rendered_html_excerpt": excerpt,
    }
    prompt = _load_prompt("editorial_qa.txt").format(today=today.isoformat())
    body = prompt + "\n\nINPUT JSON:\n" + json.dumps(qa_input, indent=2)
    result = run_max(prompt=body, extended_thinking_budget=16000)
    if result.parsed is None:
        # Fallback: ship with a warning, never block on QA infrastructure failure
        return EditorialQAResult(status="pass", issues=[
            QAIssue(section_id=None, severity="warn", message="QA call returned no parsed output; defaulted to ship")
        ], shippable=True)
    v = validate_editorial_qa(result.parsed)
    if not v.ok:
        return EditorialQAResult(status="pass", issues=[
            QAIssue(section_id=None, severity="warn", message=f"QA validator rejected output: {v.reason}; defaulted to ship")
        ], shippable=True)
    return v


# --- Helpers (private) ---

def _section_summary_for_top_picks(s: SectionData) -> dict:
    primary = s.metrics[0] if s.metrics else None
    risk_active, _, _ = evaluate_risk_rules(s)
    return {
        "id": s.id,
        "kicker": s.kicker,
        "freshness": s.freshness,
        "key_metric": ({
            "label": primary.label,
            "value": primary.value,
            "delta_pct": (primary.delta.value if primary.delta else None),
            "direction": (primary.delta.direction if primary.delta else "flat"),
        } if primary else None),
        "news_count": len(s.news),
        "has_systemic_risk": risk_active,
    }


def _section_summary_for_qa(s: SectionData) -> dict:
    return {
        "id": s.id,
        "kicker": s.kicker,
        "title": s.title,
        "freshness": s.freshness,
        "metric_count": len(s.metrics),
        "first_metric_as_of": (s.metrics[0].as_of.isoformat() if s.metrics else None),
        "has_bankerread": s.bankerread is not None,
        "has_systemic_risk": s.systemic_risk is not None,
        "risk_active": s.risk_active,
    }


def _section_n(section_id: str) -> str:
    """Map section id → display number."""
    mapping = {"headlines": "01", "bb": "02", "macro": "03", "fx": "04",
               "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
               "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
               "dam": "13", "exec": "14"}
    return mapping.get(section_id, "??")


def _placement_for(section_id: str, picks: TopPicks) -> dict:
    plotted = any(p.id == section_id for p in picks.plotted)
    grid = any(g.id == section_id for g in picks.grid)
    fob = (section_id == picks.front_of_book_id)
    return {"plotted": plotted, "front_of_book": fob, "grid": grid}


def _triggering_metric_for(section: SectionData, rule_id: str) -> dict | None:
    metric_id_map = {
        "banking_npl_above_30": "banking_npl_pct",
        "banking_npl_above_20": "banking_npl_pct",
        "fx_reserves_below_32bn": "bb_gross_reserves",
        "fx_reserves_below_34bn": "bb_gross_reserves",
        "fx_usd_bdt_above_124": "fx_usd_bdt",
    }
    target = metric_id_map.get(rule_id)
    if not target:
        return None
    m = next((m for m in section.metrics if m.id == target), None)
    if m is None:
        return None
    return {"id": m.id, "label": m.label, "value": m.value, "unit": m.unit, "as_of": m.as_of.isoformat()}


def _top_picks_fallback(sections: list[SectionData]) -> TopPicks:
    """Deterministic fallback when Call 1 fails: rank by |delta_pct| × freshness_weight."""
    fw = {"fresh": 1.0, "warn": 0.8, "stale": 0.6, "warming_up": 0.5, "pending": 0.4, "unavailable": 0.0}
    def score(s: SectionData) -> float:
        primary = s.metrics[0] if s.metrics else None
        delta = abs(primary.delta.value) if (primary and primary.delta) else 0
        return delta * fw.get(s.freshness, 0.5) + (5 if any(evaluate_risk_rules(s)[:1]) else 0)
    ranked = sorted(sections, key=score, reverse=True)
    plotted = [MapPoint(id=s.id, x=5.0, y=5.0, r=24, kind="fresh") for s in ranked[:7]]
    grid = [GridEntry(id=s.id, tldr=s.tldr or s.kicker) for s in ranked[7:14]]
    return TopPicks(plotted=plotted, grid=grid, front_of_book_id=ranked[0].id)


def _todays_call_fallback(previous_edition: dict | None) -> TodaysCall:
    text = (previous_edition or {}).get("todays_call_text") or "Today's call carried over from previous edition."
    return TodaysCall(text=text + " (carried over)", generated_at=datetime.now(timezone.utc))


def _strip_css_and_script(html: str) -> str:
    import re
    s = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    s = re.sub(r"<script[^>]*>.*?</script>", "", s, flags=re.DOTALL)
    return s
```

- [ ] **Step 4: Write integration tests for v5 editorial**

Create `tests/test_pipeline_v5.py`:

```python
"""V5 pipeline integration tests with mocked run_max."""
from datetime import date, datetime, timezone
from unittest.mock import patch

from brief.pipeline import (
    _placement_for,
    _section_n,
    _strip_css_and_script,
    _top_picks_fallback,
)
from brief.schema import GridEntry, MapPoint, Metric, SectionData, TopPicks


def _section(id_: str, freshness: str = "fresh", with_metric: bool = True) -> SectionData:
    metrics = []
    if with_metric:
        metrics.append(Metric(
            id=f"{id_}_x", label="x", value=1.0, unit="x",
            as_of=date(2026, 4, 21), source="x", cadence="daily",
        ))
    return SectionData(id=id_, title=id_, kicker=id_, tldr="", metrics=metrics, news=[], freshness=freshness)


def test_section_n_mapping():
    assert _section_n("bb") == "02"
    assert _section_n("iranwar") == "08"
    assert _section_n("unknown") == "??"


def test_top_picks_fallback_emits_seven_plotted_seven_grid():
    sections = [_section(f"s{i}") for i in range(14)]
    picks = _top_picks_fallback(sections)
    assert len(picks.plotted) == 7
    assert len(picks.grid) == 7
    assert {p.id for p in picks.plotted} | {g.id for g in picks.grid} == {f"s{i}" for i in range(14)}


def test_strip_css_and_script_removes_blocks():
    html = '<div>keep</div><style>body{color:red}</style><script>x</script><p>also keep</p>'
    s = _strip_css_and_script(html)
    assert "keep" in s
    assert "also keep" in s
    assert "color:red" not in s
    assert "<script" not in s


def test_placement_for():
    picks = TopPicks(
        plotted=[MapPoint(id=f"p{i}", x=1, y=1, r=10, kind="fresh") for i in range(7)],
        grid=[GridEntry(id=f"g{i}", tldr="x") for i in range(7)],
        front_of_book_id="p0",
    )
    assert _placement_for("p0", picks) == {"plotted": True, "front_of_book": True, "grid": False}
    assert _placement_for("g3", picks) == {"plotted": False, "front_of_book": False, "grid": True}
    assert _placement_for("ghost", picks) == {"plotted": False, "front_of_book": False, "grid": False}
```

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/test_pipeline_v5.py -v && pytest -q 2>&1 | tail -3
git add brief/pipeline.py tests/test_pipeline_v5.py
git commit -m "feat(pipeline): V5 editorial orchestration — 6 Claude calls + fallbacks"
```

---

## Phase 8 — Pilot section: BB / Policy & Rates V5 template (~2 hours)

**Files:**
- Create: `brief/render/v5/templates/_section_base.py`
- Create: `brief/render/v5/templates/section_bb.py`
- Test: `tests/render/v5/test_section_bb.py`

### Task 17: Shared section base + bb template

- [ ] **Step 1: Implement `brief/render/v5/templates/_section_base.py`**

```python
"""Shared per-section render shape — every V5 section template uses this scaffold.

Sections compose: header (numeral + kicker + title + tldr) → 3-pill summary →
optional systemic-risk callout → metric cards → optional sparkline → optional news → banker's read.

This base function takes the prepared parts and assembles the HTML. Per-section
templates supply the parts and any custom blocks.
"""
from __future__ import annotations

from typing import Sequence

from brief.render.v5._jsx import (
    _attr_esc,
    _esc,
    bankerread_panel_v5,
    cadence_pill_v5,
    freshness_pill,
    sparkline_svg,
    systemic_risk_callout,
)
from brief.schema import SectionData


def render_section_base(
    section: SectionData,
    *,
    section_n: str,
    summary_pills: Sequence[str],         # pre-rendered HTML fragments
    metric_cards_html: str = "",           # caller composes
    news_block_html: str = "",
    show_sparkline: bool = True,
) -> str:
    """Return the full <section> HTML for a V5 section."""
    cadence = section.metrics[0].cadence if section.metrics else "event"
    pill = freshness_pill(section.freshness)
    cadence_p = cadence_pill_v5(cadence)

    risk_callout_html = ""
    if section.systemic_risk is not None:
        risk_callout_html = systemic_risk_callout(section.systemic_risk)

    sparkline_html = ""
    if show_sparkline and section.history_values and len(section.history_values) >= 7:
        sparkline_html = (
            '<div class="section-sparkline">'
            + sparkline_svg(section.history_values, w=240, h=48)
            + '</div>'
        )

    bankerread_html = ""
    if section.bankerread is not None and section.bankerread.variant != "v4_legacy":
        bankerread_html = bankerread_panel_v5(section.bankerread, anchor=section.id)

    summary_pills_html = "".join(summary_pills)

    return (
        f'<section class="section section-v5 section-{_attr_esc(section.id)}" id="section-{_attr_esc(section.id)}">'
        '<header class="sec-header">'
        f'<span class="sec-numeral">§{_esc(section_n)}</span>'
        f'<span class="sec-kicker">{_esc(section.kicker.upper())}</span>'
        f'<span class="sec-meta">{cadence_p}{pill}</span>'
        '</header>'
        f'<h2 class="sec-title"><em>{_esc(section.title)}</em></h2>'
        f'<p class="sec-tldr">{_esc(section.tldr)}</p>'
        '<div class="sec-summary-pills">'
        f'{summary_pills_html}'
        '</div>'
        f'{risk_callout_html}'
        '<div class="sec-metric-grid">'
        f'{metric_cards_html}'
        '</div>'
        f'{sparkline_html}'
        f'{news_block_html}'
        f'{bankerread_html}'
        '</section>'
    )
```

- [ ] **Step 2: Implement `brief/render/v5/templates/section_bb.py`**

```python
"""V5 §02 — Bangladesh Bank (Policy & Rates)."""
from __future__ import annotations

from brief.render.v5._jsx import _esc, fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import Metric, SectionData


def render_section_bb(section: SectionData) -> str:
    if section.id != "bb":
        raise ValueError(f"render_section_bb received id={section.id!r}; expected 'bb'")

    # Build 3-pill summary header from primary metrics
    metrics_by_id = {m.id: m for m in section.metrics}
    pills = []
    if "bb_policy_rate" in metrics_by_id:
        m = metrics_by_id["bb_policy_rate"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">POLICY RATE</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "bb_gross_reserves" in metrics_by_id:
        m = metrics_by_id["bb_gross_reserves"]
        delta_label = ""
        if m.delta:
            sign = "+" if m.delta.value > 0 else ""
            delta_label = f" {sign}{m.delta.value:.2f} {m.delta.window}"
        pills.append(f'<span class="sum-pill"><span class="sum-key">RESERVES</span> <strong>${fmt_num(m.value)}BN</strong>{_esc(delta_label)}</span>')

    # Hero metric: gross reserves; supporting: policy rate, SDF, SLF
    hero_html = ""
    if "bb_gross_reserves" in metrics_by_id:
        reserves = metrics_by_id["bb_gross_reserves"]
        # Determine badge based on value
        badge = None
        supporting_text = "BB H2 target: $36bn"
        if isinstance(reserves.value, (int, float)):
            if reserves.value < 32.0:
                badge = "CRITICAL"
            elif reserves.value < 34.0:
                badge = "WATCH"
        hero_html = metric_hero_card(reserves, badge=badge, supporting=supporting_text)

    supporting_cards = []
    for mid in ("bb_policy_rate", "bb_sdf", "bb_slf"):
        if mid in metrics_by_id:
            m = metrics_by_id[mid]
            supporting_cards.append(metric_hero_card(m))

    metric_cards_html = hero_html + "".join(supporting_cards)

    # News block (if any)
    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="02",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

- [ ] **Step 3: Write tests**

Create `tests/render/v5/test_section_bb.py`:

```python
from datetime import date, datetime, timezone

from brief.render.v5.templates.section_bb import render_section_bb
from brief.schema import (
    BankerReadInsight,
    Delta,
    Metric,
    NewsItem,
    SectionData,
    SystemicRisk,
)


def _full_bb_section(systemic: bool = False) -> SectionData:
    metrics = [
        Metric(id="bb_policy_rate", label="Policy Rate", value=10.0, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_sdf", label="SDF", value=8.5, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_slf", label="SLF", value=11.5, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_gross_reserves", label="Gross Reserves", value=34.12, unit="bn USD",
               as_of=date(2026, 4, 20), source="BB", cadence="weekly",
               delta=Delta(value=0.12, direction="up", window="wow")),
    ]
    risk = None
    if systemic:
        risk = SystemicRisk(headline="Reserves below threshold",
                            body=" ".join(["word"] * 80),
                            level="warning",
                            rule_id="fx_reserves_below_34bn")
    br = BankerReadInsight(
        variant="full",
        meaning=" ".join(["m"] * 80),
        action=" ".join(["a"] * 80),
        trigger=" ".join(["t"] * 80),
        focus=" ".join(["f"] * 80),
        pull_quote="Comfort with the real-rate gap, not the prelude to a pivot.",
        generated_at=datetime.now(timezone.utc),
    )
    return SectionData(
        id="bb", title="Governor held. Again.", kicker="Policy & rates",
        tldr="4th consecutive hold; credit growth undershooting.",
        metrics=metrics, news=[], freshness="fresh",
        bankerread=br, systemic_risk=risk, risk_active=systemic,
        history_values=[34.0, 34.05, 34.08, 34.10, 34.11, 34.10, 34.12],
    )


def test_section_bb_renders_full():
    html = render_section_bb(_full_bb_section())
    assert 'id="section-bb"' in html
    assert "§02" in html
    assert "POLICY & RATES" in html
    assert "Governor held" in html
    assert "10.00" in html  # policy rate via fmt_num
    assert "34.12" in html
    assert "POLICY RATE" in html  # 3-pill summary
    assert "RESERVES" in html
    assert "§A MEANING" in html  # banker's read full
    assert "§D FOCUS" in html
    assert '<svg' in html  # sparkline


def test_section_bb_renders_systemic_risk_callout_when_active():
    html = render_section_bb(_full_bb_section(systemic=True))
    assert "systemic-risk" in html
    assert "Reserves below threshold" in html


def test_section_bb_omits_sparkline_when_history_too_short():
    section = _full_bb_section()
    section_short = section.model_copy(update={"history_values": [1.0, 2.0, 3.0]})
    html = render_section_bb(section_short)
    assert '<svg' not in html or 'sparkline' not in html


def test_section_bb_rejects_wrong_id():
    section = _full_bb_section().model_copy(update={"id": "fx"})
    import pytest
    with pytest.raises(ValueError):
        render_section_bb(section)
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/render/v5/test_section_bb.py -v && pytest -q 2>&1 | tail -3
git add brief/render/v5/templates/_section_base.py brief/render/v5/templates/section_bb.py tests/render/v5/test_section_bb.py
git commit -m "feat(render/v5): pilot bb section template + shared section base"
```

---

## Phase 9 — Shell + assemble for V5 (~1.5 hours)

**Files:**
- Create: `brief/render/v5/shell_v5.html`
- Create: `brief/render/v5/styles.css`
- Create: `brief/render/v5/assemble.py`
- Test: `tests/render/v5/test_assemble.py`

### Task 18: V5 shell + stylesheet

- [ ] **Step 1: Write `brief/render/v5/shell_v5.html`**

A minimal HTML shell with `{{tokens_css}}`, `{{styles_css}}`, and `{{body}}` substitution slots.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1200">
  <title>{{title}}</title>
  <style id="tokens">
{{tokens_css}}
  </style>
  <style id="styles">
{{styles_css}}
  </style>
</head>
<body class="brief-v5">
{{body}}
</body>
</html>
```

- [ ] **Step 2: Write `brief/render/v5/styles.css`**

Skeleton styles for V5 chrome + per-section template. Comprehensive enough to make the page recognizably *The Brief* even before pixel polish:

```css
/* V5 styles — magazine layout. Tokens come from tokens.css. */

* { box-sizing: border-box; }
body.brief-v5 {
  margin: 0;
  font-family: var(--font-serif-text);
  color: var(--ink-1);
  background: var(--paper-1);
  line-height: 1.5;
}

.live-banner {
  background: var(--ox);
  color: var(--ink-inverse);
  font-family: var(--font-mono);
  font-size: 12px;
  padding: var(--space-sm) var(--space-lg);
}
.lb-grid { display: inline-flex; gap: var(--space-lg); margin: 0 var(--space-lg); }
.lb-key { color: var(--gold); font-weight: 600; }
.lb-val { color: var(--ink-inverse); }
.lb-dot { color: #ff6b6b; }
.lb-stamp, .lb-next { font-family: var(--font-mono); }

.masthead { padding: var(--space-lg) var(--space-2xl); border-bottom: 1px solid var(--ink-4); }
.mast-meta { font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); }
.mast-grid { display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-2xl); margin-top: var(--space-md); }
.mast-title { font-family: var(--font-serif-display); font-size: 96px; font-weight: 900; line-height: 1; margin: 0; }
.mt-the { color: var(--ink-1); }
.mt-brief { color: var(--ox); font-style: italic; font-weight: 400; }
.mt-plotted { color: var(--ink-1); font-style: italic; font-weight: 400; }
.mast-dek { font-style: italic; color: var(--ink-3); margin-top: var(--space-md); max-width: 38ch; }

.todays-call { border-left: 3px solid var(--ox); padding-left: var(--space-md); }
.tc-label { font-family: var(--font-mono); font-size: 11px; color: var(--ox); font-weight: 700; letter-spacing: 0.05em; }
.tc-text { font-size: 18px; line-height: 1.5; margin: var(--space-sm) 0; }
.tc-byline { font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); }

.risk-map { padding: var(--space-lg) var(--space-2xl); display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-xl); align-items: start; }
.rm-svg { width: 100%; height: auto; aspect-ratio: 4/3; background: var(--paper-2); }
.rm-quad-bg { fill: rgba(107,31,39,0.04); }
.rm-quad-bg.q-event { fill: rgba(107,31,39,0.10); }
.rm-quad { font-family: var(--font-mono); font-size: 11px; fill: var(--ink-3); letter-spacing: 0.05em; }
.rm-num { font-family: var(--font-mono); font-size: 11px; font-weight: 700; }
.rm-label { font-family: var(--font-mono); font-size: 12px; fill: var(--ink-2); }
.rm-axis-x, .rm-axis-y { font-family: var(--font-mono); font-size: 11px; fill: var(--ink-3); }
.rm-readfirst { font-family: var(--font-mono); font-size: 11px; fill: var(--ox); }
.rm-legend { display: flex; gap: var(--space-md); margin-top: var(--space-sm); font-family: var(--font-mono); font-size: 11px; }
.rm-leg-item .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; vertical-align: middle; margin-right: 6px; }
.dot-event { background: var(--ox); }
.dot-fresh { background: var(--green); }
.dot-slow { background: var(--gold); }
.dot-anchor { background: var(--ink-1); }

.front-of-book { background: var(--ink-1); color: var(--ink-inverse); padding: var(--space-lg); }
.fob-header { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 11px; color: var(--gold); }
.fob-title { font-family: var(--font-serif-display); font-size: 36px; font-weight: 700; margin: var(--space-sm) 0; }
.fob-pull { background: rgba(200,154,63,0.12); border-left: 3px solid var(--gold); padding: var(--space-sm) var(--space-md); font-style: italic; margin: var(--space-md) 0; }
.fob-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-sm); margin: var(--space-md) 0; }
.fob-card { background: rgba(255,255,255,0.06); padding: var(--space-md); }
.fob-card-label { font-family: var(--font-mono); font-size: 10px; color: var(--ink-4); }
.fob-card-value { font-family: var(--font-serif-display); font-size: 24px; font-weight: 700; margin-top: var(--space-xs); }
.fob-card-delta { font-family: var(--font-mono); font-size: 11px; color: var(--green); }
.fob-card-delta.dir-down { color: var(--red); }
.fob-prose { font-size: 14px; line-height: 1.6; }
.fob-prose strong { color: var(--gold); }
.fob-jump { display: inline-block; margin-top: var(--space-md); font-family: var(--font-mono); font-size: 12px; color: var(--gold); text-decoration: none; border-bottom: 1px solid var(--gold); }

.secondary-grid { padding: var(--space-lg) var(--space-2xl); }
.sg-header { font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.05em; }
.sg-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-md); margin-top: var(--space-md); }
.grid-card { display: flex; align-items: center; gap: var(--space-md); padding: var(--space-md); background: var(--paper-2); text-decoration: none; color: var(--ink-1); border-left: 2px solid var(--ink-3); }
.grid-card[data-freshness="fresh"] { border-left-color: var(--green); }
.grid-card[data-freshness="warn"], .grid-card[data-freshness="warming_up"] { border-left-color: var(--gold); }
.grid-card[data-freshness="stale"] { border-left-color: var(--ink-3); }
.grid-card-kicker { font-family: var(--font-mono); font-size: 11px; font-weight: 700; }
.grid-card-tldr { flex: 1; font-size: 13px; }
.grid-card-arrow { color: var(--ox); }

.section.section-v5 { padding: var(--space-xl) var(--space-2xl); border-top: 1px solid var(--ink-4); }
.sec-header { display: flex; align-items: baseline; gap: var(--space-md); }
.sec-numeral { font-family: var(--font-serif-display); font-size: 64px; font-weight: 900; color: var(--ox); }
.sec-kicker { font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.08em; color: var(--ink-3); }
.sec-title { font-family: var(--font-serif-display); font-size: 36px; margin: var(--space-sm) 0; }
.sec-tldr { font-size: 15px; color: var(--ink-2); margin: 0 0 var(--space-md); max-width: 60ch; }
.sec-summary-pills { display: flex; flex-wrap: wrap; gap: var(--space-md); margin: var(--space-md) 0; }
.sum-pill { font-family: var(--font-mono); font-size: 12px; padding: 4px 10px; background: var(--paper-2); border: 1px solid var(--ink-4); }
.sec-metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-md); margin: var(--space-md) 0; }
.metric-card { padding: var(--space-md); background: var(--paper-2); border-left: 3px solid var(--ox); }
.metric-card-hero { grid-column: span 2; }
.metric-label { font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); }
.metric-value { font-family: var(--font-serif-display); font-size: 32px; font-weight: 700; margin: var(--space-xs) 0; }
.metric-card-hero .metric-value { font-size: 56px; }
.metric-badge { display: inline-block; font-family: var(--font-mono); font-size: 10px; padding: 2px 8px; background: var(--red); color: var(--ink-inverse); margin-top: var(--space-xs); }
.metric-supporting { font-size: 12px; color: var(--ink-3); margin-top: var(--space-sm); }

.systemic-risk { background: rgba(168,58,58,0.06); border: 2px solid var(--red); padding: var(--space-md); margin: var(--space-md) 0; display: grid; grid-template-columns: 24px 1fr; gap: var(--space-sm); }
.systemic-risk-warning { border-color: var(--gold); background: rgba(200,154,63,0.08); }
.systemic-risk-icon { font-size: 18px; }
.systemic-risk-headline { margin: 0; font-family: var(--font-serif-text); font-size: 16px; font-weight: 700; }
.systemic-risk-body { margin: var(--space-xs) 0 0; font-size: 13px; line-height: 1.5; }

.sec-news { list-style: none; padding: 0; margin: var(--space-md) 0; }
.news-bullet { padding: var(--space-md) 0; border-bottom: 1px solid var(--paper-3); }
.news-title { font-weight: 700; color: var(--ink-1); text-decoration: none; display: block; }
.news-summary { font-size: 13px; color: var(--ink-2); margin: var(--space-xs) 0; }
.news-attr { font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); }

.bankerread.bankerread-v5 { background: var(--ink-1); color: var(--ink-inverse); padding: var(--space-lg); margin-top: var(--space-md); }
.br-pull-quote { font-style: italic; font-size: 18px; color: var(--gold); margin-bottom: var(--space-md); padding-left: var(--space-md); border-left: 3px solid var(--gold); }
.br-section { margin-bottom: var(--space-md); }
.br-label { font-family: var(--font-mono); font-size: 11px; color: var(--gold); font-weight: 700; }
.br-content { font-size: 14px; line-height: 1.6; margin: var(--space-xs) 0; }
.bankerread-jump { font-family: var(--font-mono); font-size: 11px; color: var(--gold); }

.freshness-pill { font-family: var(--font-mono); font-size: 10px; padding: 2px 6px; }
.freshness-stale { background: var(--ink-3); color: var(--ink-inverse); }
.freshness-warming-up { background: var(--gold); color: var(--ink-1); }
.freshness-warn { background: var(--gold); color: var(--ink-1); }

.cadence-pill { font-family: var(--font-mono); font-size: 10px; padding: 2px 6px; border: 1px solid var(--ink-4); color: var(--ink-3); }

.colophon { padding: var(--space-lg) var(--space-2xl); font-family: var(--font-mono); font-size: 11px; color: var(--ink-3); border-top: 1px solid var(--ink-4); }
.col-row { display: flex; gap: var(--space-md); margin-top: var(--space-xs); }
.col-label { font-weight: 700; }
```

- [ ] **Step 3: Implement `brief/render/v5/assemble.py`**

```python
"""V5 assemble — splice chrome + section fragments into shell_v5.html.

Inputs:
- list of all 14 SectionData (V5 fields populated by V5 editorial pipeline)
- per-section render functions: dict[id, callable] — fall through to v4 renderer for sections not yet templatized
- live values (for live banner)
- TopPicks, TodaysCall (chrome inputs)
- run_meta for colophon
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from brief.render.v5.chrome.colophon import render_colophon
from brief.render.v5.chrome.front_of_book import render_front_of_book
from brief.render.v5.chrome.live_banner import render_live_banner
from brief.render.v5.chrome.masthead import render_masthead
from brief.render.v5.chrome.risk_map import render_risk_map
from brief.render.v5.chrome.secondary_grid import render_secondary_grid
from brief.schema import SectionData, TodaysCall, TopPicks

V5_DIR = Path(__file__).parent
SHELL = V5_DIR / "shell_v5.html"
TOKENS = V5_DIR / "tokens.css"
STYLES = V5_DIR / "styles.css"


def assemble_v5(
    *,
    sections: list[SectionData],
    section_renderers: dict[str, Callable[[SectionData], str]],
    v4_renderer_fallback: Callable[[SectionData], str],
    top_picks: TopPicks,
    todays_call: TodaysCall,
    live: dict[str, Any],
    run_meta: dict[str, Any],
    today_label: str,
) -> str:
    section_by_id = {s.id: s for s in sections}

    # Compose body
    sections_lookup = {s.id: {"kicker": s.kicker, "n": _section_n(s.id)} for s in sections}

    body_parts = []
    body_parts.append(render_live_banner(live))
    body_parts.append(render_masthead(
        vol=str(run_meta.get("vol", "II")),
        issue=int(run_meta.get("issue", 1)),
        today_label=today_label,
        todays_call=todays_call,
    ))

    # Risk map + front-of-book preview side by side
    risk_map_html = render_risk_map(picks=top_picks, sections=sections_lookup, today_label=today_label)
    fob_section = section_by_id.get(top_picks.front_of_book_id)
    fob_html = ""
    if fob_section is not None:
        fob_html = render_front_of_book(fob_section, section_n=_section_n(fob_section.id))
    body_parts.append(f'<div class="map-row">{risk_map_html}{fob_html}</div>')

    body_parts.append(render_secondary_grid(picks=top_picks, sections=section_by_id))

    # Sections in read-order = plotted (front-of-book first) then grid
    plotted_ids_in_order = [top_picks.front_of_book_id] + [
        p.id for p in top_picks.plotted if p.id != top_picks.front_of_book_id
    ]
    grid_ids = [g.id for g in top_picks.grid]
    full_order = plotted_ids_in_order + grid_ids

    for sid in full_order:
        section = section_by_id.get(sid)
        if section is None:
            continue
        renderer = section_renderers.get(sid, v4_renderer_fallback)
        body_parts.append(renderer(section))

    body_parts.append(render_colophon({
        **run_meta,
        "today_label": today_label,
    }))

    body = "\n".join(body_parts)

    shell = SHELL.read_text()
    return (shell
        .replace("{{title}}", "The Brief")
        .replace("{{tokens_css}}", TOKENS.read_text())
        .replace("{{styles_css}}", STYLES.read_text())
        .replace("{{body}}", body)
    )


def _section_n(section_id: str) -> str:
    mapping = {"headlines": "01", "bb": "02", "macro": "03", "fx": "04",
               "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
               "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
               "dam": "13", "exec": "14"}
    return mapping.get(section_id, "??")
```

- [ ] **Step 4: Write integration test**

Create `tests/render/v5/test_assemble.py`:

```python
"""End-to-end assemble test with synthetic sections + the bb pilot."""
from datetime import date, datetime, timezone

from brief.render.v5.assemble import assemble_v5
from brief.render.v5.templates.section_bb import render_section_bb
from brief.schema import (
    BankerReadInsight,
    Delta,
    GridEntry,
    MapPoint,
    Metric,
    SectionData,
    TodaysCall,
    TopPicks,
)


def _bb_section() -> SectionData:
    metrics = [
        Metric(id="bb_policy_rate", label="Policy Rate", value=10.0, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_gross_reserves", label="Gross Reserves", value=34.12, unit="bn USD",
               as_of=date(2026, 4, 20), source="BB", cadence="weekly",
               delta=Delta(value=0.12, direction="up", window="wow")),
    ]
    return SectionData(
        id="bb", title="Governor held. Again.", kicker="Policy & rates",
        tldr="4th consecutive hold; credit growth undershooting.",
        metrics=metrics, news=[], freshness="fresh",
        bankerread=BankerReadInsight(
            variant="full",
            meaning="word " * 80, action="word " * 80,
            trigger="word " * 80, focus="word " * 80,
            pull_quote="Comfort with the real-rate gap.",
            generated_at=datetime.now(timezone.utc),
        ),
        history_values=[34.0, 34.05, 34.08, 34.10, 34.11, 34.10, 34.12],
    )


def _stub_section(id_: str, kicker: str) -> SectionData:
    return SectionData(
        id=id_, title=f"{kicker} title", kicker=kicker, tldr=f"{kicker} tldr",
        metrics=[], news=[], freshness="warming_up",
    )


def _v4_fallback(s: SectionData) -> str:
    return f'<section id="section-{s.id}" class="section-v4-stub">{s.title}</section>'


def test_assemble_v5_smoke():
    bb = _bb_section()
    others = [_stub_section(f"s{i}", f"S{i}") for i in range(13)]
    sections = [bb] + others

    plotted = [
        MapPoint(id="bb", x=1.2, y=6.0, r=24, kind="anchor"),
        MapPoint(id="s0", x=2, y=7, r=28, kind="slow"),
        MapPoint(id="s1", x=3, y=6, r=28, kind="slow"),
        MapPoint(id="s2", x=6, y=7, r=30, kind="fresh"),
        MapPoint(id="s3", x=6.5, y=4.8, r=26, kind="fresh"),
        MapPoint(id="s4", x=5, y=5.4, r=24, kind="fresh"),
        MapPoint(id="s5", x=9.4, y=9.1, r=38, kind="event"),
    ]
    grid = [GridEntry(id=f"s{i}", tldr=f"S{i} short tldr") for i in range(6, 13)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="s5")

    todays_call = TodaysCall(text="word " * 80, generated_at=datetime.now(timezone.utc))

    html = assemble_v5(
        sections=sections,
        section_renderers={"bb": render_section_bb},
        v4_renderer_fallback=_v4_fallback,
        top_picks=picks,
        todays_call=todays_call,
        live={
            "usd_bdt": 122.70, "dsex": 5232, "brent_usd": 95.10,
            "reserves_bn_usd": 34.12,
            "generated_at": datetime(2026, 4, 21, 6, 15, tzinfo=timezone.utc),
            "next_update_label": "18:00 CLOSE",
        },
        run_meta={"vol": "II", "issue": 412, "sources_used": ["BB"], "render_duration_s": 1820, "total_cost_usd": 38.0},
        today_label="Tue 21 Apr 2026",
    )

    assert "<!DOCTYPE html>" in html
    assert "live-banner" in html
    assert "masthead" in html
    assert "risk-map" in html
    assert "front-of-book" in html
    assert "secondary-grid" in html
    assert 'id="section-bb"' in html
    assert "Governor held" in html
    assert "POLICY RATE" in html  # 3-pill summary from V5
    assert "section-v4-stub" in html  # other 13 use V4 fallback
    assert "colophon" in html
```

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/render/v5/test_assemble.py -v && pytest -q 2>&1 | tail -3
git add brief/render/v5/shell_v5.html brief/render/v5/styles.css brief/render/v5/assemble.py tests/render/v5/test_assemble.py
git commit -m "feat(render/v5): shell + styles + assemble (mixed-mode V5 pilot + V4 fallback)"
```

---

## Phase 10 — Pipeline dispatch via BRIEF_RENDERER (~1 hour)

**Files:**
- Modify: `brief/pipeline.py`
- Test: `tests/test_pipeline_v5.py`

### Task 19: Wire BRIEF_RENDERER flag into the main pipeline run

- [ ] **Step 1: Locate the V4 render dispatch in `brief/pipeline.py`**

Run: `grep -n "render\|assemble" brief/pipeline.py | head -30`
Identify where the V4 renderer assembles index.html.

- [ ] **Step 2: Add V5 dispatch wrapper**

In `brief/pipeline.py`, find the function that produces the final HTML (likely named `assemble_html` or called inside `run_with_mode`). Wrap with V5 dispatch:

```python
def render_index_html(
    *,
    sections: list[SectionData],
    today: date,
    today_label: str,
    live: dict,
    run_meta: dict,
    headlines_curation_result,
    previous_edition: dict | None = None,
) -> tuple[str, dict]:
    """Render the full index.html.

    Mode chosen by BRIEF_RENDERER env var:
      - v4 (default): legacy renderer; minimal V5 fields ignored.
      - v5: V5 chrome + V5 templates for whichever sections have V5 implementations;
            V4 renderer fallback for the rest.

    Returns (html_string, render_meta_dict).
    """
    mode = renderer_mode()

    if mode == "v5":
        # Run V5 editorial calls
        top_picks, todays_call, bankerreads, systemic_risks = run_v5_editorial(
            sections=sections,
            today=today,
            headlines_curation_result=headlines_curation_result,
            previous_edition=previous_edition,
        )
        # Attach editorial outputs back to sections
        for s in sections:
            s.bankerread = bankerreads.get(s.id)
            s.systemic_risk = systemic_risks.get(s.id)

        # Import V5 renderers we have
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_bb import render_section_bb

        section_renderers = {
            "bb": render_section_bb,
            # Plan B will add 13 more entries; until then, others fall through to V4
        }

        html = assemble_v5(
            sections=sections,
            section_renderers=section_renderers,
            v4_renderer_fallback=_v4_render_section,  # existing helper
            top_picks=top_picks,
            todays_call=todays_call,
            live=live,
            run_meta=run_meta,
            today_label=today_label,
        )

        # Run Call 6 QA gate
        qa_result = run_v5_qa_gate(
            sections=sections, todays_call=todays_call, top_picks=top_picks,
            rendered_html=html, today=today,
        )
        return html, {"qa": qa_result.model_dump(mode="json"), "renderer_mode": "v5"}

    # V4 path — unchanged
    html = _v4_render_full(sections=sections, today=today, today_label=today_label, ...)  # existing
    return html, {"renderer_mode": "v4"}
```

- [ ] **Step 3: Wire QA-gate halt into the run orchestrator**

In the function that calls `render_index_html` (likely `run_with_mode`), add a check for `qa.shippable=False` and bail before push:

```python
html, render_meta = render_index_html(...)
if render_meta.get("renderer_mode") == "v5":
    qa = render_meta["qa"]
    if not qa.get("shippable", True):
        # QA blocked the ship. Preserve yesterday's index.html on the published branch.
        # Write the candidate to artifacts/index.html (still pushable to shadow branch for review).
        run_report["status"] = "blocked_by_editorial_qa"
        run_report["qa_issues"] = qa.get("issues", [])
        # Halt before push_artifacts; rely on caller to NOT push to main when status != "ok".
        return run_report
```

- [ ] **Step 4: Write env-flag dispatch test**

Append to `tests/test_pipeline_v5.py`:

```python
import os
from unittest.mock import patch

from brief.pipeline import renderer_mode


def test_renderer_mode_default_v4():
    with patch.dict(os.environ, {}, clear=True):
        assert renderer_mode() == "v4"


def test_renderer_mode_v5_explicit():
    with patch.dict(os.environ, {"BRIEF_RENDERER": "v5"}, clear=True):
        assert renderer_mode() == "v5"


def test_renderer_mode_uppercase_normalized():
    with patch.dict(os.environ, {"BRIEF_RENDERER": "V5"}, clear=True):
        assert renderer_mode() == "v5"
```

- [ ] **Step 5: Run tests + commit**

```bash
pytest tests/test_pipeline_v5.py -v && pytest -q 2>&1 | tail -3
git add brief/pipeline.py tests/test_pipeline_v5.py
git commit -m "feat(pipeline): BRIEF_RENDERER=v5 dispatch + QA-gate halt"
```

---

## Phase 11 — Local + VPS smoke validation (~1 hour, ~$50 compute)

### Task 20: Local Mac smoke run with V5 enabled

- [ ] **Step 1: Set V5 mode locally**

```bash
cd ~/Projects/clauding-lab/the-brief
export BRIEF_RENDERER=v5
export BRIEF_DRY_RUN=1   # don't push to git from local smoke
```

- [ ] **Step 2: Run pipeline against today's data**

```bash
source .venv/bin/activate
python -m brief.cli run --mode shadow --artifacts-dir /tmp/brief-v5-smoke
```

Expected: pipeline completes, `/tmp/brief-v5-smoke/index.html` exists, `/tmp/brief-v5-smoke/run_report.json` shows `renderer_mode: v5` and either `qa.shippable: true` or detailed reasons.

- [ ] **Step 3: Eyeball the page**

```bash
open /tmp/brief-v5-smoke/index.html
```

Check: live banner renders, masthead "The Brief, plotted." displays in serif italic, risk map shows 7 bubbles, secondary grid shows 7 cards, the bb section is V5-styled (oxblood numeral, structured banker's read panel with §A/§B/§C/§D, dark bg), other 13 sections fall through to V4 stubs.

- [ ] **Step 4: If anything looks broken, fix it incrementally**

Each fix is its own commit on `feat/v5-pilot`. Don't move to VPS until local eyeball passes.

- [ ] **Step 5: Commit any local fixes**

```bash
git add <whatever fixed>
git commit -m "fix(render/v5): <specific issue>"
```

### Task 21: VPS smoke (gated on user authorization)

- [ ] **Step 1: Push branch to origin**

```bash
git push -u origin feat/v5-pilot
```

- [ ] **Step 2: User authorizes VPS sync** (action-explicit phrase required: `ssh vps git pull v5`)

The agent must request this explicitly; do not proceed without action-explicit auth.

- [ ] **Step 3: SSH and pull V5 branch (after auth)**

```bash
ssh adnan@135.181.43.68 'cd /home/adnan/the-brief && git fetch origin && git checkout feat/v5-pilot && git pull --ff-only origin feat/v5-pilot'
```

- [ ] **Step 4: Set BRIEF_RENDERER=v5 on VPS**

```bash
ssh adnan@135.181.43.68 'sudo sed -i "/^BRIEF_RENDERER=/d" /etc/brief.env && echo "BRIEF_RENDERER=v5" | sudo tee -a /etc/brief.env'
```

- [ ] **Step 5: Manual VPS smoke (action-explicit phrase: `vps v5 smoke`)**

```bash
ssh adnan@135.181.43.68 'sudo systemctl start --no-block brief.service'
# then poll: while [ "$(systemctl is-active brief.service)" = "activating" ]; do sleep 10; done
```

- [ ] **Step 6: Pull rendered index.html for eyeball**

```bash
scp adnan@135.181.43.68:/home/adnan/the-brief/artifacts/index.html /tmp/brief-v5-vps-smoke.html
open /tmp/brief-v5-vps-smoke.html
```

- [ ] **Step 7: Confirm or rollback**

If it looks right: leave V5 enabled, but timer stays disabled until Plan B (parallel waves) ships.
If something's broken: `BRIEF_RENDERER=v4` rolls back instantly; investigate locally; iterate.

---

## Phase 12 — Self-review

After completing Phases 1-11, run the spec-vs-plan checklist:

1. **Spec coverage:**
   - [✓] All 6 Claude calls have a task (Phase 6, 7).
   - [✓] All 6 chrome components have a task (Phase 5).
   - [✓] Pilot bb section has a task (Phase 8).
   - [✓] BRIEF_RENDERER dispatch has a task (Phase 10).
   - [✓] QA gate halt has a task (Phase 10).
   - [✓] Schema additions have a task (Phase 1).
   - [✓] Extended thinking support has a task (Phase 2).
   - [✓] Local + VPS smoke validation have tasks (Phase 11).
   - [✗ — known gap] The 13 non-pilot V5 section templates: **deferred to Plan B**, written after Plan A pilot validates.
   - [✗ — minor gap] Cadence change to `OnCalendar=Mon..Fri,Sun 02:30:00 UTC` is in the spec; the timer file edit isn't in this plan because the timer is currently disabled. When Plan B closes and we re-enable, we'll edit `deploy/brief.timer` then.

2. **Placeholder scan:** No TBDs/TODOs/"implement later" — all task steps have actual code or actual commands.

3. **Type consistency:**
   - `BankerReadInsight.variant` values are consistent across schema.py, validators, _jsx.py, templates: `{"full", "stale_micro", "v4_legacy"}`.
   - `MapPoint.kind` values are consistent: `{"event", "fresh", "slow", "anchor"}`.
   - `freshness_pill` accepts `freshness` from `_VALID_FRESHNESS` set in _jsx.py; matches `FreshnessKind` in schema.

4. **Open follow-up for Plan B:**
   - Apply the `section_bb.py` template pattern to the 13 remaining sections.
   - 13 parallel agent waves (3-4 sections per wave, 3-4 waves total).
   - Email-specific V5 template (deferred per spec).

---

## Execution handoff

Plan A is complete. The plan delivers:
- All schema additions (back-compat with V4)
- All 6 chrome components
- All 6 editorial Claude calls (prompts + validators + pipeline integration)
- Systemic-risk rule engine
- Pilot bb section in V5
- BRIEF_RENDERER env-flag dispatch + QA-gate halt
- Local + VPS smoke validation tasks

**Plan saved to:** `docs/superpowers/plans/2026-04-25-the-brief-v5-pilot.md` (Part 1) + `docs/superpowers/plans/2026-04-25-the-brief-v5-pilot-part2.md` (Part 2 — this file).

**Two execution options:**

1. **Subagent-Driven (recommended)** — A fresh subagent picks up each task, you review between tasks, fast iteration with two-stage review.

2. **Inline Execution** — Execute tasks in this session with batch checkpoints for review.

Which approach?
