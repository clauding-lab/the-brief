# The Brief — V5 Plan B Wave 3 design

**Date:** 2026-04-29
**Author:** Adnan Rashid (with Claude)
**Status:** Approved (brainstorm complete; awaiting implementation plan via writing-plans skill)
**Predecessor:** [V5 Plan B design](./2026-04-29-the-brief-v5-plan-b-design.md) — Wave 1 (PR #21) and Wave 2 (PR #22) merged 2026-04-29
**Sibling specs:** [V5 design (Plan A)](./2026-04-25-the-brief-v5-design.md), [V5 Plan B design](./2026-04-29-the-brief-v5-plan-b-design.md)

---

## 1. Goal

Complete the V5 magazine layout by replacing the last four `<section-v4-stub>` placeholders — Headlines, Iran War & Oil, Banking, Executive Signals — with real V5 templates. After Wave 3 merges, every section in the brief renders in V5 shape and Plan B is complete.

**In scope:** 4 new section templates + supporting tests + dispatcher wiring.
**Out of scope:** New CSS for `hl-grid`, `hl-lead`, `oil-events`, `exec-signals` classes (visual polish is a follow-up); modifications to `_section_base.py`, `_jsx.py`, builders, schema, or any V4 code.

## 2. Decisions captured during brainstorm

1. **Hybrid complexity strategy.** Port what's structurally cheap from V4; drop what isn't. Skip the V4 italic-oxblood emphasis heuristic, the V4 3-tier headlines grid, and the V4 12-session Brent SVG with overlaid event pins. Keep the editorial signal of each section through simpler shapes.
2. **`_section_base.py` stays unchanged.** No new parameters, no `news-led` flag. The `news_block_html` parameter already accepts arbitrary HTML and serves as the generic content slot for sections that need bespoke layouts (headlines, iranwar oil-events strip, exec signals list).
3. **Exec signals as list-of-callouts.** Each signal renders as a one-line item with a direction-coloured chevron + text + a "→ §NN" anchor link. New CSS classes (`exec-signals`, `exec-signal-bull/bear/warn/watch`) deferred to a styling pass.
4. **Iranwar event pins separated from the chart.** Standard V5 sparkline carries the brent price line; events render as a compact strip below the metric cards in `news_block_html`.
5. **Headlines as lead + 6-bullet list.** First headline gets a fuller treatment (title + source + first ~30 words as dek); remaining 6 render as compact `news_bullet` items in a standard `<ul class="sec-news">`.
6. **Banking threshold matches the systemic-risk engine.** `npl > 30` → CRITICAL, `npl > 20` → WATCH. Spec §6's "npl > 12 → WATCH" trigger is rejected as too low for Bangladesh sector data.

## 3. File layout after Wave 3 (changes only)

```
brief/
├── pipeline.py              # MODIFIED — section_renderers dict grows from 10 → 14
└── render/
    └── v5/
        └── templates/
            ├── section_headlines.py    # NEW Wave 3 — §01 lead + 6 bullets, no hero
            ├── section_iranwar.py      # NEW Wave 3 — §08 brent hero + events strip
            ├── section_banking.py      # NEW Wave 3 — §09 npl hero + standard pattern
            └── section_exec.py         # NEW Wave 3 — §14 list-of-callouts, no metrics
```

After this PR merges, the dispatch table covers all 14 section IDs in the system; the `_v4_render_section_stub` fallback path becomes unreachable in the V5 mode under normal operation.

## 4. Per-section design

### §01 Headlines

Bespoke "lead + 6 bullets" shape inside `news_block_html`:

```python
def render_section_headlines(section: SectionData) -> str:
    if section.id != "headlines":
        raise ValueError(...)

    pills = []
    metrics_by_id = {m.id: m for m in section.metrics}
    if "headlines_count" in metrics_by_id:
        m = metrics_by_id["headlines_count"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">HEADLINES</span> <strong>{int(m.value)}</strong></span>')

    # No hero, no supporting cards — news_block_html does the work
    metric_cards_html = ""

    news_html = ""
    if section.news:
        lead = section.news[0]
        rest = section.news[1:7]  # next 6
        dek = _first_n_words(getattr(lead, "summary", "") or lead.title, n=30)
        lead_html = (
            f'<article class="hl-lead">'
            f'<div class="hl-lead-source">{_esc(lead.source)}</div>'
            f'<h3 class="hl-lead-title"><a href="{_attr_esc(lead.url)}">{_esc(lead.title)}</a></h3>'
            f'<p class="hl-lead-dek">{_esc(dek)}</p>'
            f'</article>'
        )
        bullets_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in rest)
        news_html = f'<div class="hl-grid">{lead_html}<ul class="sec-news">{bullets_html}</ul></div>'

    return render_section_base(
        section,
        section_n="01",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=False,  # no 7-point series for headlines count
    )
```

`_first_n_words(text, n)` is a 3-line local helper (split + slice + join). No new helpers in `_jsx.py`.

### §08 Iran War & Oil

Standard hero + supporting + sparkline + events strip:

```python
def render_section_iranwar(section: SectionData) -> str:
    if section.id != "iranwar":
        raise ValueError(...)

    metrics_by_id = {m.id: m for m in section.metrics}
    events = section.extras.get("oil_events", []) if isinstance(section.extras, dict) else []
    if not isinstance(events, list):
        events = []

    pills = []
    if "iranwar_brent_spot" in metrics_by_id:
        pills.append(...)  # BRENT
    if "iranwar_wti_spot" in metrics_by_id:
        pills.append(...)  # WTI
    if events:
        pills.append(f'<span class="sum-pill"><span class="sum-key">EVENTS</span> <strong>{len(events)}</strong></span>')

    hero_html = ""
    if "iranwar_brent_spot" in metrics_by_id:
        hero = metrics_by_id["iranwar_brent_spot"]
        badge = None
        if isinstance(hero.value, (int, float)) and hero.value > 100.0:
            badge = "CRITICAL"
        hero_html = metric_hero_card(hero, badge=badge, supporting="EconDelta daily spot")

    supporting_cards = []
    if "iranwar_wti_spot" in metrics_by_id:
        supporting_cards.append(metric_hero_card(metrics_by_id["iranwar_wti_spot"]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    # Events strip + news bullets — both go into news_block_html
    events_strip = ""
    if events:
        items = []
        for ev in events[:6]:  # cap at 6 for layout
            label = _event_label(ev)
            ev_date = _event_date_short(ev)
            arrow = "▲" if _event_is_hot(ev) else "◯"
            items.append(f'<span class="oil-event"><span class="oil-arrow">{_esc(arrow)}</span> {_esc(ev_date)} {_esc(label)}</span>')
        events_strip = f'<div class="oil-events">{" · ".join(items)}</div>'

    news_html_inner = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html_inner = f'<ul class="sec-news">{items_html}</ul>'

    news_block = events_strip + news_html_inner

    return render_section_base(
        section,
        section_n="08",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_block,
        show_sparkline=True,
    )
```

`_event_label`, `_event_date_short`, `_event_is_hot` are 3 local helpers (~5 lines each). They handle both the `OilEvent` dataclass shape and the dict shape that the builder serialises. Mirrors V4's defensive pattern.

### §09 Banking

Standard pattern matching Wave 1/2 templates:

```python
def render_section_banking(section: SectionData) -> str:
    if section.id != "banking":
        raise ValueError(...)

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "banking_npl_pct" in metrics_by_id:
        pills.append(...)  # NPL
    if "banking_car_pct" in metrics_by_id:
        pills.append(...)  # CAR

    hero_html = ""
    if "banking_npl_pct" in metrics_by_id:
        hero = metrics_by_id["banking_npl_pct"]
        badge = None
        if isinstance(hero.value, (int, float)):
            if hero.value > 30.0:
                badge = "CRITICAL"
            elif hero.value > 20.0:
                badge = "WATCH"
        hero_html = metric_hero_card(hero, badge=badge, supporting="BB quarterly release")

    supporting_cards = []
    if "banking_car_pct" in metrics_by_id:
        supporting_cards.append(metric_hero_card(metrics_by_id["banking_car_pct"]))

    metric_cards_html = hero_html + "".join(supporting_cards)

    news_html = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_html = f'<ul class="sec-news">{items_html}</ul>'

    return render_section_base(
        section,
        section_n="09",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_html,
        show_sparkline=True,
    )
```

### §14 Executive Signals

List-of-callouts. No metrics, no sparkline:

```python
_EXEC_DIRECTION_ARROW = {"bull": "▲", "bear": "▼", "warn": "⚠", "watch": "◐"}

_EXEC_ANCHOR_TO_N = {
    "headlines": "01", "bb": "02", "macro": "03", "fx": "04",
    "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
    "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
    "dam": "13", "exec": "14",
}

def render_section_exec(section: SectionData) -> str:
    if section.id != "exec":
        raise ValueError(...)

    pills = []  # no pills

    metric_cards_html = ""  # no metric cards

    signals = section.exec_signals or []
    signals_html = ""
    if signals:
        items = []
        for sig in signals:
            arrow = _EXEC_DIRECTION_ARROW.get(sig.direction, "◐")
            anchor_n = _EXEC_ANCHOR_TO_N.get(sig.section_anchor, "??")
            items.append(
                f'<li class="exec-signal exec-signal-{_attr_esc(sig.direction)}">'
                f'<span class="exec-arrow">{_esc(arrow)}</span>'
                f'<span class="exec-text">{_esc(sig.text)}</span>'
                f'<a class="exec-anchor" href="#section-{_attr_esc(sig.section_anchor)}">→ §{_esc(anchor_n)}</a>'
                f'</li>'
            )
        signals_html = f'<ul class="exec-signals">{"".join(items)}</ul>'

    return render_section_base(
        section,
        section_n="14",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=signals_html,
        show_sparkline=False,
    )
```

The `_EXEC_ANCHOR_TO_N` map is duplicated from `pipeline_v5.py::_section_n` — DRY-vs-decoupling tradeoff resolved in favour of decoupling: the render layer stays self-contained without importing from the pipeline. If this map changes, both copies update; the section count is fixed at 14, so drift risk is minimal.

## 5. Per-section parameters summary

| Section | §NN | Hero | Supporting | Pills | Sparkline | Threshold |
|---|---|---|---|---|---|---|
| **headlines** | 01 | (none) | (none) | HEADLINES count | no | none |
| **iranwar** | 08 | `iranwar_brent_spot` | `iranwar_wti_spot` (1 only) | BRENT, WTI, EVENTS | yes | brent > 100 → CRITICAL |
| **banking** | 09 | `banking_npl_pct` | `banking_car_pct` (1 only) | NPL, CAR | yes | npl > 30 → CRITICAL, > 20 → WATCH |
| **exec** | 14 | (none) | (none) | (none) | no | none |

## 6. Testing strategy

Per spec §7 of the parent design doc, 5 tests per section. Total Wave 3: +20 → **677**.

| Section | Test 1 | Test 2 | Test 3 | Test 4 | Test 5 |
|---|---|---|---|---|---|
| headlines | renders_with_full_data | renders_with_no_metrics | renders_with_no_news | no_threshold_badge_in_render | rejects_wrong_id |
| iranwar | renders_with_full_data | renders_with_no_metrics | renders_with_no_events | threshold_badge_brent_above_100 | rejects_wrong_id |
| banking | renders_with_full_data | renders_with_no_metrics | renders_with_no_news | threshold_badge_npl_above_30 | rejects_wrong_id |
| exec | renders_with_full_data | renders_with_no_signals | renders_with_one_signal | no_threshold_badge_in_render | rejects_wrong_id |

The per-section "test 3" varies: headlines/banking use `no_news`, iranwar uses `no_events`, exec uses `with_one_signal` (since news isn't applicable to exec). The 5-test pattern bends to fit the section's actual content surface.

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| New CSS classes (`hl-grid`, `hl-lead`, `oil-events`, `exec-signals`, `exec-signal-*`, `exec-arrow`, `exec-text`, `exec-anchor`, `oil-event`, `oil-arrow`) render unstyled in production | Certain | Visual polish miss in V5 | PR description flags this; styling pass is a follow-up PR. Tests assert HTML structure, not visual rendering. |
| Exec signal direction value from Claude doesn't match the 4 SignalKind literals | Low | Default `◐` arrow renders | Pydantic schema validation rejects non-Literal values upstream; template's `.get(direction, "◐")` is a belt-and-braces guard |
| Headlines lead has empty `summary` and a 1-word `title` | Low | `dek` text empty; lead block renders without dek paragraph | `_first_n_words` returns empty string; lead block's `<p class="hl-lead-dek"></p>` renders empty (cosmetic glitch, not a render failure) |
| `iranwar.section.extras["oil_events"]` is missing or non-iterable | Medium | Events strip absent; section still renders | `section.extras.get("oil_events", [])` + `isinstance(list)` defensive checks; no events strip rendered when data is bad |
| `banking.section.metrics` is missing both NPL and CAR (V4 builder degraded path) | Low | Empty metric_cards_html; section renders header + news + bankerread | Standard graceful-fallback pattern; one of Wave 3's 5 tests covers this |
| Hardcoded `_EXEC_ANCHOR_TO_N` drifts from `pipeline_v5._section_n` | Low | Exec signals link to wrong §NN labels | Section count is fixed at 14; if Plan B adds a new section ID, both maps update together. Future-Wave changes will surface this. |
| Test count for Wave 3 ≠ +20 | Low | Acceptance criteria miss | Spec §6 above pins 5 per section × 4 sections; deviating sections (exec test 3 swap) still net to 5 |

## 8. Acceptance for Wave 3 (and full Plan B)

When all four templates are merged into `feat/v4-retarget`:

- 677/677 tests passing
- 0 `<section-v4-stub>` markers in any V5 HTML render
- All 14 sections render in V5 shape (verified locally and on VPS)
- PR #23 merged
- The `_v4_render_section_stub` function in `pipeline.py` becomes unreachable in V5 mode (cleanup deferred to a separate PR or kept as defensive fallback)

## 9. Out-of-scope notes (parked for future)

- **CSS for the new classes** — `hl-grid`, `hl-lead*`, `oil-events`, `oil-event`, `oil-arrow`, `exec-signals`, `exec-signal*`, `exec-arrow`, `exec-text`, `exec-anchor`. A separate styling PR after Wave 3 merges.
- **Event pin overlay on the iranwar Brent chart** — V4 has it; V5 explicitly drops it in favor of the events strip. Could revisit if reader feedback says the chronological alignment carries information the strip doesn't.
- **Headlines "italic-oxblood" emphasis on the last word** — V4 has it; V5 drops it as a visual tic without clear editorial value.
- **`headlines_count` as a hero** — considered, rejected. The count is meta, not editorial; pill is enough.
- **Banking with deposits_yoy or LDR** — spec §6 wanted these as supporting cards; V4 builder doesn't expose them. A builder enhancement could add them; out of Wave 3 scope.
- **Exec signal "thumbs-up/thumbs-down" reactions** — out of scope. Read-only render.
- **Tiered model routing** — long-parked, post-Plan-B decision.
- **Re-enabling `brief.timer` on VPS** — separate operational decision.
