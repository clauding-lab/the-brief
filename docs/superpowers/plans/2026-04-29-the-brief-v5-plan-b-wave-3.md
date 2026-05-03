# V5 Plan B — Wave 3: Banking, Iran War, Headlines, Exec templates (PR #23)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the final four V5 section templates — Banking (§09), Iran War & Oil (§08), Headlines (§01), Executive Signals (§14) — completing V5 Plan B. After this PR merges, every section in the daily brief renders in V5 shape.

**Architecture:** Pure additive change. Four new template modules under `brief/render/v5/templates/`, four new test files, the `section_renderers` dict in `brief/pipeline.py` extended from 10 entries to 14. **No edits** to `_section_base.py`, `_jsx.py`, builders, or schema. The `news_block_html` parameter on `render_section_base` is used as a generic content slot for sections that need bespoke HTML (headlines lead+bullets, iranwar events strip, exec signals list).

**Tech Stack:** Python 3.14, pytest. No new dependencies.

**Spec reference:** [docs/superpowers/specs/2026-04-29-the-brief-v5-plan-b-wave-3-design.md](../specs/2026-04-29-the-brief-v5-plan-b-wave-3-design.md). Per-section parameters and HTML shapes are normative there; this plan provides the executable steps.

**Wave 1 + 2 references:** Wave 1 (PR #21) and Wave 2 (PR #22) merged 2026-04-29 — together they shipped the bb scaffold + 9 templates following the standard hero/supporting/pills pattern.

**Branch:** `feat/v5-wave3` (already cut from `feat/v4-retarget` after PR #22 merged; spec doc commit `c061852` already on this branch).

**Estimated session length:** ~3-4 hours with subagents (4 templates of varying complexity + integration + push).

---

## Per-section context (read before any task)

> The Wave 3 design spec is the source of truth. This plan executes against §4 of the spec. Key reminders:

- **No `_section_base.py` modifications.** All bespoke HTML goes through `news_block_html` (which is content-agnostic).
- **Section numbers** from `brief/pipeline_v5.py::_section_n`: headlines=01, iranwar=08, banking=09, exec=14.
- **Real V4 builder data shapes**:
  - `headlines`: 1 metric (`headlines_count`), 8+ NewsItems
  - `iranwar`: 2 metrics (`iranwar_brent_spot`, `iranwar_wti_spot`), `section.extras["oil_events"]` list of OilEvent dataclass instances
  - `banking`: 2 metrics (`banking_npl_pct`, `banking_car_pct`)
  - `exec`: 0 metrics, `section.exec_signals: list[ExecSignal] | None`
- **CSS** for new classes (`hl-grid`, `hl-lead*`, `oil-events`, `oil-event`, `oil-arrow`, `exec-signals`, `exec-signal-*`, `exec-arrow`, `exec-text`, `exec-anchor`) is **out of scope**. Tests assert HTML structure, not visual rendering. PR description flags this.

---

## Pre-flight check

- [ ] **Step 1: Confirm branch state.**

```bash
cd ~/Projects/clauding-lab/the-brief
git status --short --branch
```

Expected: `## feat/v5-wave3` (with or without `...origin/feat/v5-wave3` — both fine).

- [ ] **Step 2: Confirm spec doc is the only commit ahead of `feat/v4-retarget`.**

```bash
git log --oneline feat/v4-retarget..HEAD
```

Expected: one line — `c061852 docs(spec): V5 Plan B Wave 3 design — 4 final templates` (or whatever cherry-picked SHA).

- [ ] **Step 3: Verify baseline test count.**

```bash
source .venv/bin/activate
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `657 passed in <N>s` where `<N>` is 15-40s. If 60+, suspect mock-bypass; STOP.

- [ ] **Step 4: Confirm Wave 1 + Wave 2 templates are present.**

```bash
ls brief/render/v5/templates/
```

Expected (alphabetical):
```
__init__.py    _section_base.py    section_bb.py    section_comm.py    section_dam.py
section_dse.py    section_fiscal.py    section_fx.py    section_macro.py    section_nbr.py
section_remit.py    section_tbond.py
```

If any are missing, the merge state is wrong — STOP.

---

## Task 1: Banking section (`§09`) — simplest, builds confidence

**Files:**
- Create: `brief/render/v5/templates/section_banking.py`
- Create: `tests/render/v5/test_section_banking.py`

**Goal:** Render banking with NPL hero + CAR supporting. Threshold: `npl > 30` → CRITICAL, `npl > 20` → WATCH (matches the existing systemic-risk rule pair).

- [ ] **Step 1: Write the test file (5 tests, fail-first).**

Create `tests/render/v5/test_section_banking.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_banking import render_section_banking
from brief.schema import Metric, NewsItem, SectionData


def _banking_section(*, with_metrics: bool = True, with_news: bool = True,
                     npl: float = 11.5) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="banking_npl_pct", label="NPL Ratio", value=npl, unit="%",
                   as_of=date(2026, 3, 31), source="BB", cadence="quarterly"),
            Metric(id="banking_car_pct", label="CAR", value=11.8, unit="%",
                   as_of=date(2026, 3, 31), source="BB", cadence="quarterly"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Q1 NPL ratio holds steady", url="https://example.com/banking1",
                     source="The Daily Star", published=datetime(2026, 4, 5, tzinfo=timezone.utc)),
        ]
    return SectionData(
        id="banking", title="Banking",
        kicker="BANKING", tldr=f"NPL: {npl}%; CAR: 11.8%",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[10.5, 10.8, 11.0, 11.2, 11.3, 11.4, npl],
    )


def test_section_banking_renders_with_full_metrics():
    html = render_section_banking(_banking_section())
    assert 'id="section-banking"' in html
    assert "§09" in html
    assert "BANKING" in html
    assert "Banking" in html
    assert "11.50" in html
    assert "NPL" in html
    assert "CAR" in html


def test_section_banking_renders_with_no_metrics():
    html = render_section_banking(_banking_section(with_metrics=False))
    assert 'id="section-banking"' in html
    assert "metric-card" not in html


def test_section_banking_renders_with_no_news():
    html = render_section_banking(_banking_section(with_news=False))
    assert 'id="section-banking"' in html
    assert '<ul class="sec-news">' not in html


def test_section_banking_threshold_badge_npl_above_30():
    # npl = 32 → CRITICAL
    html_crit = render_section_banking(_banking_section(npl=32.0))
    assert "CRITICAL" in html_crit
    # npl = 22 → WATCH (above 20 but below 30)
    html_watch = render_section_banking(_banking_section(npl=22.0))
    assert "WATCH" in html_watch
    assert "CRITICAL" not in html_watch


def test_section_banking_rejects_wrong_id():
    section = _banking_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_banking(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_banking.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_banking.py`:

```python
"""V5 §09 — Banking."""
from __future__ import annotations

from brief.render.v5._jsx import fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def render_section_banking(section: SectionData) -> str:
    if section.id != "banking":
        raise ValueError(f"render_section_banking received id={section.id!r}; expected 'banking'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "banking_npl_pct" in metrics_by_id:
        m = metrics_by_id["banking_npl_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">NPL</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "banking_car_pct" in metrics_by_id:
        m = metrics_by_id["banking_car_pct"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">CAR</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')

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

- [ ] **Step 4: Run tests, expect all pass.**

```bash
python -m pytest tests/render/v5/test_section_banking.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `662 passed in <N>s`. (Previous 657 + 5 new banking tests.) If `<N>` > 60s, mock-bypass — STOP.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_banking.py tests/render/v5/test_section_banking.py
git commit -m "feat(v5): add Banking section template (§09)

Hero: banking_npl_pct. Supporting: banking_car_pct (1 only — V4 builder
exposes only NPL and CAR). Pills: NPL, CAR. Threshold: npl > 30 →
CRITICAL, > 20 → WATCH (matches systemic-risk rules
banking_npl_above_30 / banking_npl_above_20).

5 unit tests. Tests: 657 → 662."
```

---

## Task 2: Iran War & Oil section (`§08`) — events strip + standard hero

**Files:**
- Create: `brief/render/v5/templates/section_iranwar.py`
- Create: `tests/render/v5/test_section_iranwar.py`

**Goal:** Render iranwar with brent hero + WTI supporting + custom oil-events strip rendered inside `news_block_html` ahead of news bullets. Threshold: brent > 100 → CRITICAL.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_iranwar.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_iranwar import render_section_iranwar
from brief.schema import Metric, NewsItem, SectionData


@dataclass(frozen=True)
class _OilEvent:
    """Test mirror of brief.builders.iranwar.OilEvent."""
    date: date
    label: str
    hot: bool


def _iranwar_section(*, with_metrics: bool = True, with_news: bool = True,
                     with_events: bool = True, brent: float = 84.20) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="iranwar_brent_spot", label="Brent spot", value=brent, unit="USD/bbl",
                   as_of=date(2026, 4, 28), source="EconDelta", cadence="daily"),
            Metric(id="iranwar_wti_spot",   label="WTI spot",   value=brent - 4.0, unit="USD/bbl",
                   as_of=date(2026, 4, 28), source="EconDelta", cadence="daily"),
        ]
    news = []
    if with_news:
        news = [
            NewsItem(title="Brent hovers in mid-80s as Iran tensions ease", url="https://example.com/iw1",
                     source="Reuters", published=datetime(2026, 4, 28, tzinfo=timezone.utc)),
        ]
    section = SectionData(
        id="iranwar", title="Iran War & Oil",
        kicker="GLOBAL OIL", tldr=f"Brent ${brent}/bbl",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[83.0, 83.5, 83.8, 84.0, 84.1, 84.15, brent],
    )
    if with_events:
        section.extras["oil_events"] = [
            _OilEvent(date=date(2026, 4, 21), label="Hormuz tanker", hot=True),
            _OilEvent(date=date(2026, 4, 11), label="OPEC+ hold", hot=False),
            _OilEvent(date=date(2026, 4, 2),  label="IAEA report", hot=False),
        ]
    return section


def test_section_iranwar_renders_with_full_data():
    html = render_section_iranwar(_iranwar_section())
    assert 'id="section-iranwar"' in html
    assert "§08" in html
    assert "GLOBAL OIL" in html
    assert "Iran War" in html
    assert "84.20" in html
    assert "BRENT" in html
    assert "WTI" in html
    assert "EVENTS" in html
    assert "Hormuz tanker" in html
    assert "oil-events" in html


def test_section_iranwar_renders_with_no_metrics():
    html = render_section_iranwar(_iranwar_section(with_metrics=False))
    assert 'id="section-iranwar"' in html
    assert "metric-card" not in html


def test_section_iranwar_renders_with_no_events():
    html = render_section_iranwar(_iranwar_section(with_events=False))
    assert 'id="section-iranwar"' in html
    assert "oil-events" not in html
    assert "Hormuz tanker" not in html


def test_section_iranwar_threshold_badge_brent_above_100():
    html = render_section_iranwar(_iranwar_section(brent=105.0))
    assert "CRITICAL" in html


def test_section_iranwar_rejects_wrong_id():
    section = _iranwar_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_iranwar(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_iranwar.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_iranwar.py`:

```python
"""V5 §08 — Global Oil (Iran War & Oil)."""
from __future__ import annotations

from brief.render.v5._jsx import _esc, fmt_num, metric_hero_card, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def _event_label(ev: object) -> str:
    if isinstance(ev, dict):
        return str(ev.get("label", ""))
    return str(getattr(ev, "label", ""))


def _event_date_short(ev: object) -> str:
    """Return 'Apr 21' style short date from a dict or OilEvent-like object."""
    if isinstance(ev, dict):
        d = ev.get("date", "")
        if not d:
            return ""
        if hasattr(d, "strftime"):
            return d.strftime("%b %d")
        s = str(d)[:10]
        try:
            from datetime import date as _date
            return _date.fromisoformat(s).strftime("%b %d")
        except (ValueError, TypeError):
            return s
    d = getattr(ev, "date", None)
    if d is None:
        return ""
    if hasattr(d, "strftime"):
        return d.strftime("%b %d")
    return str(d)[:10]


def _event_is_hot(ev: object) -> bool:
    if isinstance(ev, dict):
        return str(ev.get("hotness", "")).lower() == "hot"
    hot_attr = getattr(ev, "hot", None)
    if hot_attr is not None:
        return bool(hot_attr)
    return False


def render_section_iranwar(section: SectionData) -> str:
    if section.id != "iranwar":
        raise ValueError(f"render_section_iranwar received id={section.id!r}; expected 'iranwar'")

    metrics_by_id = {m.id: m for m in section.metrics}
    extras = section.extras if isinstance(section.extras, dict) else {}
    events_raw = extras.get("oil_events", [])
    events = events_raw if isinstance(events_raw, list) else []

    pills = []
    if "iranwar_brent_spot" in metrics_by_id:
        m = metrics_by_id["iranwar_brent_spot"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">BRENT</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
    if "iranwar_wti_spot" in metrics_by_id:
        m = metrics_by_id["iranwar_wti_spot"]
        pills.append(f'<span class="sum-pill"><span class="sum-key">WTI</span> <strong>{fmt_num(m.value, unit=m.unit)}</strong></span>')
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

    events_strip = ""
    if events:
        items = []
        for ev in events[:6]:
            arrow = "▲" if _event_is_hot(ev) else "◯"
            items.append(
                f'<span class="oil-event"><span class="oil-arrow">{_esc(arrow)}</span> {_esc(_event_date_short(ev))} {_esc(_event_label(ev))}</span>'
            )
        events_strip = f'<div class="oil-events">{" · ".join(items)}</div>'

    news_inner = ""
    if section.news:
        items_html = "".join(news_bullet(n, summary=getattr(n, "summary", "")) for n in section.news[:3])
        news_inner = f'<ul class="sec-news">{items_html}</ul>'

    news_block = events_strip + news_inner

    return render_section_base(
        section,
        section_n="08",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_block,
        show_sparkline=True,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_iranwar.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `667 passed in <N>s`. If `<N>` > 60s, mock-bypass — STOP.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_iranwar.py tests/render/v5/test_section_iranwar.py
git commit -m "feat(v5): add Iran War & Oil section template (§08)

Hero: iranwar_brent_spot. Supporting: iranwar_wti_spot (1 only). Pills:
BRENT, WTI, EVENTS. Threshold: brent > 100 → CRITICAL.

Custom oil-events strip rendered ahead of news bullets in
news_block_html. Reads section.extras['oil_events'] defensively (handles
both OilEvent dataclass and dict shapes from V4 builder serialisation).
Standard sparkline carries the brent price line; V4's overlaid event
pins are dropped per spec §2 decision 4.

5 unit tests. Tests: 662 → 667."
```

---

## Task 3: Headlines section (`§01`) — lead + 6 bullets

**Files:**
- Create: `brief/render/v5/templates/section_headlines.py`
- Create: `tests/render/v5/test_section_headlines.py`

**Goal:** Render headlines with `headlines_count` as a single pill, no hero/supporting cards, news rendered as a "lead article + 6 bullets" hl-grid layout.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_headlines.py`:

```python
from datetime import date, datetime, timezone

import pytest

from brief.render.v5.templates.section_headlines import render_section_headlines
from brief.schema import Metric, NewsItem, SectionData


def _headlines_section(*, with_metrics: bool = True, with_news: bool = True,
                       news_count: int = 8) -> SectionData:
    metrics: list[Metric] = []
    if with_metrics:
        metrics = [
            Metric(id="headlines_count", label="Headlines count", value=news_count,
                   unit="items", as_of=date(2026, 4, 28), source="scraper", cadence="daily"),
        ]
    news: list[NewsItem] = []
    if with_news and news_count > 0:
        # Lead has a longer summary so the dek extraction is exercised.
        news.append(NewsItem(
            title="Bangladesh Bank holds policy rate at 10% for fourth consecutive meeting",
            url="https://example.com/lead",
            source="The Daily Star",
            published=datetime(2026, 4, 28, 9, 0, tzinfo=timezone.utc),
        ))
        for i in range(2, news_count + 1):
            news.append(NewsItem(
                title=f"Headline number {i}",
                url=f"https://example.com/h{i}",
                source="Reuters",
                published=datetime(2026, 4, 28, tzinfo=timezone.utc),
            ))
    return SectionData(
        id="headlines", title="Headlines",
        kicker="HEADLINES", tldr=f"{news_count} curated stories",
        metrics=metrics, news=news, freshness="fresh",
        history_values=[],
    )


def test_section_headlines_renders_with_full_data():
    html = render_section_headlines(_headlines_section())
    assert 'id="section-headlines"' in html
    assert "§01" in html
    assert "HEADLINES" in html
    # Pill with the count
    assert "<strong>8</strong>" in html
    # Lead article block
    assert "hl-lead" in html
    assert "Bangladesh Bank holds policy rate" in html
    # Standard bullets follow (rest items 2..7 should appear; item 8 should be capped)
    assert "Headline number 2" in html
    assert "Headline number 7" in html
    assert "Headline number 8" not in html  # only 6 bullets after the lead
    # No metric_hero_card output
    assert "metric-card" not in html


def test_section_headlines_renders_with_no_metrics():
    html = render_section_headlines(_headlines_section(with_metrics=False))
    assert 'id="section-headlines"' in html
    # No metric pill when no metric (sum-pill is the pill class)
    assert '<span class="sum-pill">' not in html


def test_section_headlines_renders_with_no_news():
    html = render_section_headlines(_headlines_section(with_news=False))
    assert 'id="section-headlines"' in html
    assert "hl-lead" not in html
    assert "hl-grid" not in html


def test_section_headlines_no_threshold_badge_in_render():
    """Headlines has no hero metric; badge must never appear."""
    html_low  = render_section_headlines(_headlines_section(news_count=1))
    html_high = render_section_headlines(_headlines_section(news_count=99))
    assert "CRITICAL" not in html_low and "CRITICAL" not in html_high
    assert "WATCH" not in html_low and "WATCH" not in html_high


def test_section_headlines_rejects_wrong_id():
    section = _headlines_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_headlines(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_headlines.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_headlines.py`:

```python
"""V5 §01 — Headlines."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc, news_bullet
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


def _first_n_words(text: str, n: int = 30) -> str:
    """Return the first n whitespace-separated words of text, joined by space."""
    if not text:
        return ""
    parts = text.split()
    return " ".join(parts[:n])


def render_section_headlines(section: SectionData) -> str:
    if section.id != "headlines":
        raise ValueError(f"render_section_headlines received id={section.id!r}; expected 'headlines'")

    metrics_by_id = {m.id: m for m in section.metrics}

    pills = []
    if "headlines_count" in metrics_by_id:
        m = metrics_by_id["headlines_count"]
        try:
            count_val = int(m.value) if m.value is not None else 0
        except (TypeError, ValueError):
            count_val = 0
        pills.append(f'<span class="sum-pill"><span class="sum-key">HEADLINES</span> <strong>{count_val}</strong></span>')

    metric_cards_html = ""

    news_html = ""
    if section.news:
        lead = section.news[0]
        rest = section.news[1:7]
        dek_source = getattr(lead, "summary", "") or lead.title
        dek = _first_n_words(dek_source, n=30)
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
        show_sparkline=False,
    )
```

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_headlines.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `672 passed in <N>s`. If `<N>` > 60s, mock-bypass — STOP.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_headlines.py tests/render/v5/test_section_headlines.py
git commit -m "feat(v5): add Headlines section template (§01)

Hero: none (no editorially-meaningful hero metric for headlines).
Pill: HEADLINES count. Bespoke 'lead + 6 bullets' layout in
news_block_html — first NewsItem renders as a hl-lead article block,
items 2-7 render as standard sec-news bullets. Item 8+ is dropped to
respect layout discipline.

V4's 3-tier hl-grid (lead + right column + bottom row) and
italic-oxblood emphasis on the lead title's last word are dropped per
spec §2 decision 5.

5 unit tests including 'no badge ever' guard. Tests: 667 → 672."
```

---

## Task 4: Executive Signals section (`§14`) — list-of-callouts

**Files:**
- Create: `brief/render/v5/templates/section_exec.py`
- Create: `tests/render/v5/test_section_exec.py`

**Goal:** Render exec with a custom signals list. No metrics, no sparkline, no news. Each signal item has a direction-coloured chevron + text + a "→ §NN" link to the anchored section.

- [ ] **Step 1: Write the test file.**

Create `tests/render/v5/test_section_exec.py`:

```python
import pytest

from brief.render.v5.templates.section_exec import render_section_exec
from brief.schema import ExecSignal, SectionData


def _exec_section(*, signals: list[ExecSignal] | None = None) -> SectionData:
    if signals is None:
        signals = [
            ExecSignal(direction="bull", text="Reserves rebuild remains intact through Q1.",
                       section_anchor="bb"),
            ExecSignal(direction="bear", text="Headline CPI base effects fade in May.",
                       section_anchor="macro"),
            ExecSignal(direction="warn", text="USD/BDT mid drifts above 124 trigger.",
                       section_anchor="fx"),
            ExecSignal(direction="watch", text="OPEC+ output decision next week.",
                       section_anchor="iranwar"),
        ]
    return SectionData(
        id="exec", title="Executive Signals",
        kicker="EXEC SIGNALS", tldr=f"{len(signals)} signals",
        metrics=[], news=[], freshness="fresh" if signals else "pending",
        exec_signals=signals or None,
    )


def test_section_exec_renders_with_full_data():
    html = render_section_exec(_exec_section())
    assert 'id="section-exec"' in html
    assert "§14" in html
    assert "EXEC SIGNALS" in html
    # All four direction classes present
    assert "exec-signal-bull" in html
    assert "exec-signal-bear" in html
    assert "exec-signal-warn" in html
    assert "exec-signal-watch" in html
    # Direction arrows
    assert "▲" in html  # bull
    assert "▼" in html  # bear
    # Signal text
    assert "Reserves rebuild" in html
    # Anchor links resolve to §NN
    assert "→ §02" in html  # bb section
    assert "→ §03" in html  # macro section
    assert "→ §04" in html  # fx section
    assert "→ §08" in html  # iranwar section
    # No metric cards, no sparkline
    assert "metric-card" not in html
    assert "sparkline" not in html


def test_section_exec_renders_with_no_signals():
    html = render_section_exec(_exec_section(signals=[]))
    assert 'id="section-exec"' in html
    assert "exec-signals" not in html
    assert "exec-signal-" not in html


def test_section_exec_renders_with_one_signal():
    one = [ExecSignal(direction="bull", text="Solo signal.", section_anchor="bb")]
    html = render_section_exec(_exec_section(signals=one))
    assert "exec-signal-bull" in html
    assert "Solo signal." in html
    assert "→ §02" in html
    # Only one li
    assert html.count('class="exec-signal ') == 1


def test_section_exec_no_threshold_badge_in_render():
    """Exec has no metrics; badge must never appear."""
    html = render_section_exec(_exec_section())
    assert "CRITICAL" not in html
    assert "WATCH" not in html


def test_section_exec_rejects_wrong_id():
    section = _exec_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_exec(section)
```

- [ ] **Step 2: Run failing tests.**

```bash
python -m pytest tests/render/v5/test_section_exec.py --no-cov -v 2>&1 | tail -20
```

Expected: 5 fails with `ModuleNotFoundError`.

- [ ] **Step 3: Write the template.**

Create `brief/render/v5/templates/section_exec.py`:

```python
"""V5 §14 — Executive Signals."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc
from brief.render.v5.templates._section_base import render_section_base
from brief.schema import SectionData


_EXEC_DIRECTION_ARROW = {
    "bull": "▲",
    "bear": "▼",
    "warn": "⚠",
    "watch": "◐",
}

_EXEC_ANCHOR_TO_N = {
    "headlines": "01", "bb": "02", "macro": "03", "fx": "04",
    "remit": "05", "dse": "06", "tbond": "07", "iranwar": "08",
    "banking": "09", "comm": "10", "fiscal": "11", "nbr": "12",
    "dam": "13", "exec": "14",
}


def render_section_exec(section: SectionData) -> str:
    if section.id != "exec":
        raise ValueError(f"render_section_exec received id={section.id!r}; expected 'exec'")

    pills: list[str] = []
    metric_cards_html = ""

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

- [ ] **Step 4: Run tests.**

```bash
python -m pytest tests/render/v5/test_section_exec.py --no-cov -v 2>&1 | tail -20
```

Expected: `5 passed`.

- [ ] **Step 5: Run full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `677 passed in <N>s`. If `<N>` > 60s, mock-bypass — STOP.

- [ ] **Step 6: Commit.**

```bash
git add brief/render/v5/templates/section_exec.py tests/render/v5/test_section_exec.py
git commit -m "feat(v5): add Executive Signals section template (§14)

Hero: none (exec is signals-led, not metric-led). Bespoke list-of-
callouts in news_block_html: each ExecSignal renders as <li> with a
direction chevron (bull=▲, bear=▼, warn=⚠, watch=◐), the signal text,
and a '→ §NN' anchor link to section_anchor.

The _EXEC_ANCHOR_TO_N map is duplicated locally rather than imported
from pipeline_v5 to keep the render layer self-contained. Section IDs
are stable; drift risk is minimal.

5 unit tests covering full data, no signals, single signal, no badge
ever, wrong-id ValueError. Tests: 672 → 677."
```

---

## Task 5: Wire Wave 3 templates into the V5 dispatcher

**Files:**
- Modify: `brief/pipeline.py:646-670` (the V5 mode block in `render_index_html` — section_renderers dict + the import block)

**Goal:** Extend the `section_renderers` dict from 10 entries (bb + Wave 1 + Wave 2) to 14 (full coverage).

- [ ] **Step 1: Read the current dispatch block.**

```bash
sed -n '640,675p' brief/pipeline.py
```

Expected: shows the 10-import block + 10-entry dict from PR #22.

- [ ] **Step 2: Apply the edit.**

In `brief/pipeline.py`, replace the existing 10-import block:

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

with:

```python
        from brief.render.v5.assemble import assemble_v5
        from brief.render.v5.templates.section_banking import render_section_banking
        from brief.render.v5.templates.section_bb import render_section_bb
        from brief.render.v5.templates.section_comm import render_section_comm
        from brief.render.v5.templates.section_dam import render_section_dam
        from brief.render.v5.templates.section_dse import render_section_dse
        from brief.render.v5.templates.section_exec import render_section_exec
        from brief.render.v5.templates.section_fiscal import render_section_fiscal
        from brief.render.v5.templates.section_fx import render_section_fx
        from brief.render.v5.templates.section_headlines import render_section_headlines
        from brief.render.v5.templates.section_iranwar import render_section_iranwar
        from brief.render.v5.templates.section_macro import render_section_macro
        from brief.render.v5.templates.section_nbr import render_section_nbr
        from brief.render.v5.templates.section_remit import render_section_remit
        from brief.render.v5.templates.section_tbond import render_section_tbond
```

(All 14 imports alphabetical.)

And replace the existing dict:

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

with:

```python
        section_renderers: dict = {
            "banking": render_section_banking,
            "bb": render_section_bb,
            "comm": render_section_comm,
            "dam": render_section_dam,
            "dse": render_section_dse,
            "exec": render_section_exec,
            "fiscal": render_section_fiscal,
            "fx": render_section_fx,
            "headlines": render_section_headlines,
            "iranwar": render_section_iranwar,
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

- [ ] **Step 4: Confirm a V5-mode dispatch covers all 14 sections.**

```bash
python -c "
from brief.render.v5.templates.section_banking import render_section_banking
from brief.render.v5.templates.section_exec import render_section_exec
from brief.render.v5.templates.section_headlines import render_section_headlines
from brief.render.v5.templates.section_iranwar import render_section_iranwar
print('all four Wave 3 templates importable')
"
```

Expected: `all four Wave 3 templates importable`.

- [ ] **Step 5: Run the full suite.**

```bash
python -m pytest --no-cov -q 2>&1 | tail -3
```

Expected: `677 passed in <N>s`. Same count as Task 4.

- [ ] **Step 6: Commit.**

```bash
git add brief/pipeline.py
git commit -m "feat(v5): wire Headlines/Iran War/Banking/Exec into V5 dispatcher

Extends the section_renderers dict in pipeline.py from 10 entries to 14
— full coverage of all section IDs. After this commit, V5 mode renders
every section in editorial shape; the _v4_render_section_stub fallback
becomes unreachable in V5 mode under normal operation.

Imports re-sorted alphabetically.

Tests: 677/677 (unchanged — dispatch wiring isn't asserted by unit tests;
smoke render is the human-eyeballed gate)."
```

---

## Task 6: Local smoke render (user-gated)

**Goal:** Optional local smoke render to eyeball all 14 sections in V5 shape. Real Claude calls (~$7-12). User decides whether to run.

- [ ] **Step 1: Stop and ask.**

> "Wave 3 templates done locally. 677/677 tests passing. Three options for smoke render: (a) run it now (~$7-12 in real Claude calls); (b) skip smoke, ship the PR; (c) you run the smoke yourself. Which?"

Wait for explicit choice.

- [ ] **Step 2: If (a), run the smoke.**

```bash
mkdir -p /tmp/wave3-smoke
BRIEF_RENDERER=v5 python -m brief.cli run --artifacts-dir /tmp/wave3-smoke 2>&1 | tail -20
```

Expected: completes in 200-400 seconds, exits 0, deposits `index.html`.

- [ ] **Step 3: Verify zero v4-stub markers.**

```bash
grep -c "section-v4-stub" /tmp/wave3-smoke/index.html
```

Expected: `0`. Plan B is structurally complete when this returns 0.

- [ ] **Step 4: Verify the four new sections rendered.**

```bash
for sid in headlines iranwar banking exec; do
  count=$(grep -c "id=\"section-${sid}\"" /tmp/wave3-smoke/index.html)
  echo "${sid}: ${count}"
done
```

Expected: each prints `1`.

- [ ] **Step 5: Open in the browser and eyeball.**

```bash
open /tmp/wave3-smoke/index.html
```

Inspect: §01 Headlines lead + 6 bullets renders; §08 Iran War shows brent hero + WTI supporting + events strip; §09 Banking shows NPL hero with badge if value > 20; §14 Exec Signals shows the list with direction chevrons. Visually rough is OK — CSS for new classes is deferred.

- [ ] **Step 6: Record outcome (no commit).**

Read-only task.

---

## Task 7: Push and open PR (gated on user approval)

**Goal:** Push `feat/v5-wave3` and open PR #23 against `feat/v4-retarget`.

- [ ] **Step 1: Stop and ask.**

> "Wave 3 done locally. 677/677 tests passing. Six commits on `feat/v5-wave3` (1 spec doc + 4 templates + 1 dispatcher wire). May I push to origin and open PR #23 against `feat/v4-retarget`?"

Wait for action-explicit approval.

- [ ] **Step 2: Push.**

```bash
git push -u origin feat/v5-wave3
```

- [ ] **Step 3: Open the PR.**

```bash
gh pr create --base feat/v4-retarget --head feat/v5-wave3 --title "feat(v5): Wave 3 — Headlines, Iran War, Banking, Exec Signals (Plan B complete)" --body "$(cat <<'EOF'
## Summary

V5 Plan B Wave 3 — the final four section templates. After this PR merges, every section in the daily brief renders in V5 shape; the `<section-v4-stub>` fallback path becomes unreachable in V5 mode.

- **§01 Headlines** — `headlines_count` pill, bespoke "lead article + 6 bullets" layout. No hero, no sparkline, no threshold.
- **§08 Iran War & Oil** — hero `iranwar_brent_spot`; `iranwar_wti_spot` supporting; oil-events strip rendered ahead of news bullets. Threshold: brent > 100 → CRITICAL.
- **§09 Banking** — hero `banking_npl_pct`; `banking_car_pct` supporting. Threshold: npl > 30 → CRITICAL, > 20 → WATCH (matches the systemic-risk rule pair).
- **§14 Executive Signals** — bespoke list-of-callouts: each `ExecSignal` renders as `<li>` with a direction chevron (bull=▲, bear=▼, warn=⚠, watch=◐), the signal text, and a `→ §NN` anchor link.

The `section_renderers` dict in `pipeline.py` grows from 10 entries to 14 — full coverage.

### Spec deviations from V5 Plan B §6

- `_section_base.py` stays unchanged. `news_block_html` is used as a generic content slot for headlines' lead+bullets layout, iranwar's events strip, and exec's signals list.
- Headlines drops the V4 3-tier grid (lead + right column + bottom row) and the italic-oxblood emphasis heuristic.
- Iran War drops the V4 SVG with overlaid event pins; uses the standard sparkline + a separate compact events strip.
- Banking threshold uses the systemic-risk engine's existing thresholds (30 / 20) rather than the spec's "12% → WATCH" trigger.

Section numbers from `pipeline_v5._section_n`: headlines=01, iranwar=08, banking=09, exec=14.

### Test plan

- [x] 5 unit tests per section × 4 sections = +20 tests; suite 657 → 677 passing
- [x] Each test file covers: full-data, no-metrics/no-signals, no-news/no-events/one-signal, threshold-badge or "no badge ever" guard, wrong-id ValueError
- [x] All four template modules under 90 lines (banking 50, iranwar 90, headlines 55, exec 60)
- [ ] Manual: local smoke render (per-PR decision; see Task 6 in plan)
- [ ] Manual: full Plan B acceptance — `grep -c section-v4-stub` returns 0 on smoke render

### Out of scope

- **CSS for the new classes** — `hl-grid`, `hl-lead*`, `oil-events`, `oil-event`, `oil-arrow`, `exec-signals`, `exec-signal-*`, `exec-arrow`, `exec-text`, `exec-anchor`. A separate styling PR after Wave 3 merges. HTML structure is in place; visual polish lands later.
- **Cleanup of `_v4_render_section_stub` from `pipeline.py`** — keep as defensive fallback for now.
- Tiered model routing — long-parked.
- Re-enabling `brief.timer` on VPS — separate operational decision, post-Plan B.
EOF
)"
```

- [ ] **Step 4: Verify PR state.**

```bash
gh pr view --json number,state,mergeable,baseRefName,headRefName,additions,deletions,changedFiles
```

Expected: `state=OPEN`, `mergeable=MERGEABLE`, `changedFiles=10` (4 templates + 4 tests + 1 modified pipeline.py + 1 spec doc).

---

## Acceptance criteria for PR #23

When all seven tasks are checked off:

- ✓ Four new files under `brief/render/v5/templates/`: `section_banking.py`, `section_iranwar.py`, `section_headlines.py`, `section_exec.py` — each ≤90 lines.
- ✓ Four new test files under `tests/render/v5/`: `test_section_banking.py`, `test_section_iranwar.py`, `test_section_headlines.py`, `test_section_exec.py` — each with 5 tests.
- ✓ `brief/pipeline.py` `section_renderers` dict has 14 entries (full coverage).
- ✓ All 677 tests pass; no regression in the previous 657.
- ✓ Test suite runs in 15-40 seconds.
- ✓ Local smoke (Task 6) eyeballed and approved (or explicitly skipped).
- ✓ PR #23 open against `feat/v4-retarget`, MERGEABLE, CLEAN.
- ✓ Spec doc `docs/superpowers/specs/2026-04-29-the-brief-v5-plan-b-wave-3-design.md` is part of the PR diff.

After PR #23 merges, V5 Plan B is complete. Parked items (tiered model routing, CSS pass for the new classes, `brief.timer` re-enable on VPS) become the next set of decisions.
