"""Per-metric vintage: how old a printed number actually is, in plain words.

Why this exists
---------------
Issue #184 printed *"REER at 102.78 keeping the taka dear as the peg eases to
123.82"* — a **March** index and **that day's** spot rate, in one clause, with
nothing anywhere recording that the two were five months apart. A reader takes
both for current, because nothing in the sentence says otherwise.

The Brief already computed freshness, but only per SECTION, and only as a badge
colour. Two gaps followed:

1. **The editor never saw which individual numbers were old.** `as_of` reached
   it inside the metric dump, but no threshold came with it, so "2026-03-01"
   was just a string. It sometimes wrote "Mar print" and sometimes didn't —
   there was no rule, and a metric borrowed into another section's prose (the
   REER clause above) lost even that.
2. **The render never printed a vintage.** `Section.tsx` has had a "held from"
   footer since v1.2.0, but the only thing that ever populated `held_from` was
   `mark_held_overs`, which reads `section_slug` and `last_print_date` from the
   `metric_definitions` catalog — **neither column exists in production**. It
   has been a no-op for its whole life: 0 of the last 1000 published metric
   rows carry `held_from`. The footer has never once rendered.

`metric_vintage` closes both: one deterministic answer to "how old is this
number", stamped into the editor's input BEFORE the prose is written and onto
the published metric AFTER, so the two cannot disagree.

What counts as a vintage
------------------------
Anything past its cadence's FRESH threshold — i.e. `warning` or `stale` in
`brief.cadence`. A fresh metric gets none; saying "as of today" on today's
number is noise, and noise is how a real staleness signal gets ignored.

Why there is no "next print"
----------------------------
v1.6.4 carried a `next_print` hint (as_of + a per-cadence interval). It was
removed in v1.6.5 because it is **unreachable by construction**: a vintage only
exists once a metric is past its cadence's fresh threshold, and every fresh
threshold is LONGER than that cadence's publication interval —

    monthly    vintage at >35d, interval 30d
    weekly     vintage at  >7d, interval  7d
    quarterly  vintage at >95d, interval 91d
    daily      vintage at  >1 trading day, interval 1d

— so `as_of + interval` has always already passed by the time anything asks. It
rendered live as *"As of 2026-03-01 · next print Mar 2026"*: a next print in the
same month as the as-of. Rolling it forward to the next future period was
rejected as the worse fix — REER has never been collected by anyone, so any
date offered would be an invented schedule, and the whole value of this module
is that its output can be trusted. "Overdue" is in `note`; that is the honest
version, and it is a fact rather than a forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from brief.cadence import metric_freshness
from brief.schema import Metric, SectionData

if TYPE_CHECKING:  # pragma: no cover — annotation only
    from brief.v6_schema import BriefPayloadV6

@dataclass(frozen=True)
class Vintage:
    """How old one printed number is, and how to say so.

    `label` is the reader-facing period ("Mar 2026", "Q1 2026"). `note` is the
    fuller phrase handed to the editor.

    There is deliberately no `next_print`. v1.6.4 shipped one and it could never
    have been right — see the module note below.
    """

    as_of: date
    age_days: int
    freshness: str  # "warning" | "stale"
    cadence: str
    label: str
    note: str


def _period_label(as_of: date, cadence: str) -> str:
    """Name the period at the precision the cadence actually carries.

    A monthly series has no meaningful day-of-month — `as_of` is whichever day
    the period got stamped to — so printing "1 Mar 2026" for it invents
    precision the number does not have.
    """
    if cadence == "quarterly":
        return f"Q{(as_of.month - 1) // 3 + 1} {as_of.year}"
    if cadence == "monthly":
        return as_of.strftime("%b %Y")
    # daily / weekly / event / anything unknown: the exact day is the period.
    return as_of.strftime("%-d %b %Y")


def _note(label: str, age_days: int, cadence: str, freshness: str) -> str:
    """The phrase the editor reads. Written to be usable in prose as-is."""
    if cadence == "event":
        # A standing value's as_of is a daily RESTAMP date, not a decision date
        # (AGENTS.md landmine 24). "Last confirmed" is the only honest reading:
        # the number may well still be in force, but nobody has said so lately.
        return (
            f"last confirmed {label}, {age_days} days ago — the writer has "
            "stopped restamping it; do not present it as confirmed-current"
        )
    plural = "day" if age_days == 1 else "days"
    if freshness == "stale":
        # P0 honesty fix (2026-08-22 audit #204): "overdue" accused the SOURCE
        # (e.g. Bangladesh Bank) of not publishing, when all the pipeline
        # actually knows is that ITS OWN read is old — BB may well have
        # published five times since. State the fact (our read's age), not an
        # inference about the source's behaviour.
        return (
            f"{label} print — our latest read, {age_days}d old; name the "
            "period in any sentence that uses this number"
        )
    return f"{label} print, {age_days} {plural} old — name the period if you pair it with a current number"


def metric_vintage(metric: Metric, *, today: date | None = None) -> Vintage | None:
    """Return the vintage of `metric`, or None if it is fresh or has no value.

    Never raises. A metric whose cadence the freshness table does not know
    returns None rather than a guess — an invented vintage is worse than none,
    because the whole point of the field is that it can be trusted.
    """
    freshness = metric_freshness(metric, today=today)
    if freshness not in ("warning", "stale"):
        return None

    if today is None:
        from brief.cadence import now_bdt

        today = now_bdt().date()

    age_days = (today - metric.as_of).days
    cadence = str(metric.cadence)
    label = _period_label(metric.as_of, cadence)
    return Vintage(
        as_of=metric.as_of,
        age_days=age_days,
        freshness=freshness,
        cadence=cadence,
        label=label,
        note=_note(label, age_days, cadence, freshness),
    )


def vintage_payload(metric: Metric, *, today: date | None = None) -> dict | None:
    """`metric_vintage` as the JSON dict stamped into the editor's input."""
    v = metric_vintage(metric, today=today)
    if v is None:
        return None
    return {
        "as_of": v.as_of.isoformat(),
        "age_days": v.age_days,
        "freshness": v.freshness,
        "period_label": v.label,
        "note": v.note,
    }


def stamp_vintages(
    current: "BriefPayloadV6",
    sections: list[SectionData],
    *,
    today: date | None = None,
) -> int:
    """Stamp `held_from` onto every published metric that is old.

    Returns the number of metrics stamped.

    `next_print` is deliberately left alone. This function has no honest value
    for it (see the module note), and blanking it would clobber `mark_held_overs`
    on the day the catalog is fixed — that path reads a real publication date
    and is the only thing entitled to write the field.

    Runs AFTER `mark_held_overs` and never overwrites it: a metric the catalog
    could explain keeps the catalog's answer. Everything else gets its vintage
    from the number's own `as_of`, which the builder set and which needs no
    catalog to be true.

    This is what makes the footer real. `mark_held_overs` has been the only
    writer of `held_from` since v1.2.0, and it reads `section_slug` and
    `last_print_date` off `metric_definitions` — **neither column exists in
    production**, so every lookup missed and 0 of the last 1000 published metric
    rows carried a vintage. The footer, the CSS class and the render branch have
    all been live and unreachable the whole time.

    Matching is by (section slug, metric label), the same key `stamp_changed`
    and `mark_held_overs` already use — the editor passes labels through
    verbatim, which is why that key works.
    """
    # Imported lazily: pipeline_v6 imports this module, so a module-level
    # import of its slug map would close a cycle.
    from brief.pipeline_v6 import V5_TO_V6

    by_key: dict[tuple[str, str], Metric] = {}
    for s in sections:
        slug = V5_TO_V6[s.id][0] if s.id in V5_TO_V6 else s.id
        for m in s.metrics:
            by_key[(slug, m.label)] = m

    stamped = 0
    for section in current.sections:
        for pub in section.metrics:
            if pub.held_from is not None:
                continue
            src = by_key.get((section.slug, pub.label))
            if src is None:
                continue
            v = metric_vintage(src, today=today)
            if v is None:
                continue
            pub.held_from = v.as_of
            stamped += 1
    return stamped
