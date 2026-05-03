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
        section_n="09",
        summary_pills=pills,
        metric_cards_html=metric_cards_html,
        news_block_html=news_block,
        show_sparkline=True,
    )
