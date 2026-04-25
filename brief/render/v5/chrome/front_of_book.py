"""V5 front-of-book preview — pulled-in version of today's #1 section."""
from __future__ import annotations

from brief.render.v5._jsx import _attr_esc, _esc, fmt_num
from brief.schema import SectionData


def render_front_of_book(section: SectionData, *, section_n: str) -> str:
    br = section.bankerread

    pull_html = ""
    if br and br.pull_quote:
        pull_html = f'<div class="fob-pull"><em>{_esc(br.pull_quote)}</em></div>'

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

    action_block = ""
    if br and br.action:
        action_block = f'<p class="fob-prose"><strong>Action.</strong> {_esc(br.action)}</p>'
    trigger_block = ""
    if br and br.trigger:
        trigger_block = f'<p class="fob-prose"><strong>Trigger.</strong> {_esc(br.trigger)}</p>'

    return (
        '<aside class="front-of-book" aria-label="Front-of-book section preview">'
        '<header class="fob-header">'
        f'<span class="fob-eyebrow">§{_esc(section_n)} {_esc(section.kicker)}</span>'
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
