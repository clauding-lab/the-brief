"""Tests for per-metric vintages.

The bug these exist to stop: issue #184 printed *"REER at 102.78 keeping the
taka dear as the peg eases to 123.82"* — a March index and that day's spot rate
in one clause, with nothing recording the five-month gap.

Two halves are tested. That the vintage is COMPUTED correctly and only for
numbers that are genuinely old, and that it reaches BOTH consumers: the editor
(before the prose is written) and the published metric (after).
"""
from __future__ import annotations

from datetime import date

from brief.schema import Metric, SectionData
from brief.vintage import metric_vintage, stamp_vintages, vintage_payload

TODAY = date(2026, 8, 3)


def _m(
    metric_id: str = "reer_monthly",
    *,
    label: str = "REER",
    value: float | None = 102.78,
    as_of: date = date(2026, 3, 1),
    cadence: str = "monthly",
    stale: bool = False,
) -> Metric:
    return Metric(
        id=metric_id,
        label=label,
        value=value,
        unit="index",
        as_of=as_of,
        source="BB",
        cadence=cadence,  # type: ignore[arg-type]
        stale=stale,
    )


# ── when a vintage exists at all ─────────────────────────────────────────────

def test_a_fresh_metric_has_no_vintage() -> None:
    """"As of today" on today's number is noise, and noise is how a real
    staleness signal gets ignored."""
    assert metric_vintage(_m(as_of=date(2026, 7, 20)), today=TODAY) is None


def test_a_metric_past_its_fresh_threshold_has_a_vintage() -> None:
    v = metric_vintage(_m(as_of=date(2026, 6, 15)), today=TODAY)  # 49d, monthly
    assert v is not None
    assert v.freshness == "stale"
    assert v.age_days == 49


def test_a_metric_in_the_warning_band_has_a_vintage_too() -> None:
    """Warning is the band where a number is worth dating but not worth
    apologising for — it must still carry a date."""
    v = metric_vintage(_m(as_of=date(2026, 6, 25)), today=TODAY)  # 39d → warning
    assert v is not None
    assert v.freshness == "warning"


def test_a_valueless_metric_has_no_vintage() -> None:
    """An unavailable metric is already rendered as unavailable; dating a blank
    would put an as-of footer under an empty tile."""
    assert metric_vintage(_m(value=None), today=TODAY) is None


def test_an_unknown_cadence_has_no_vintage() -> None:
    """Forward-compat: the day someone adds a cadence to `CadenceKind` without
    teaching `brief.cadence` its thresholds, this must go quiet rather than
    guess. An invented vintage is worse than none — the whole point of the
    field is that it can be trusted.

    `model_construct` bypasses validation because `CadenceKind` is a closed
    Literal today; the guard exists for when it isn't."""
    m = Metric.model_construct(
        id="x", label="X", value=1.0, unit="index",
        as_of=date(2026, 1, 1), source="BB", cadence="fortnightly", stale=False,
    )
    assert metric_vintage(m, today=TODAY) is None


# ── the labels ───────────────────────────────────────────────────────────────

def test_a_monthly_vintage_names_the_month_not_the_day() -> None:
    """A monthly series has no meaningful day-of-month — as_of is whichever day
    the period got stamped to, so "1 Mar" invents precision the number lacks."""
    v = metric_vintage(_m(as_of=date(2026, 3, 1)), today=TODAY)
    assert v is not None
    assert v.label == "Mar 2026"


def test_a_quarterly_vintage_names_the_quarter() -> None:
    v = metric_vintage(
        _m(as_of=date(2026, 3, 31), cadence="quarterly"), today=TODAY
    )
    assert v is not None
    assert v.label == "Q1 2026"


def test_a_vintage_offers_no_next_print_date() -> None:
    """v1.6.4 shipped one; it was unreachable by construction. A vintage only
    exists once a metric is past its cadence's FRESH threshold, and every fresh
    threshold is longer than that cadence's publication interval (monthly 35 vs
    30, weekly 7 vs 7, quarterly 95 vs 91), so `as_of + interval` has always
    already passed. It rendered live as "As of 2026-03-01 · next print Mar 2026".

    Rolling it forward to the next future period was the worse fix: REER has
    never been collected by anyone, so any date offered would be invented."""
    v = metric_vintage(_m(), today=TODAY)
    assert v is not None
    assert not hasattr(v, "next_print")


def test_a_daily_vintage_names_the_exact_day() -> None:
    v = metric_vintage(_m(as_of=date(2026, 7, 14), cadence="daily"), today=TODAY)
    assert v is not None
    assert v.label == "14 Jul 2026"


def test_the_reer_case_reads_as_a_march_print() -> None:
    """The literal #184 metric, at the age it actually had."""
    v = metric_vintage(_m(as_of=date(2026, 3, 1)), today=TODAY)
    assert v is not None
    assert v.age_days == 155
    assert "Mar 2026" in v.note
    assert "155d old" in v.note


def test_a_stale_vintage_note_does_not_blame_the_source() -> None:
    """P0 honesty fix (2026-08-22 audit #204): "overdue" accused the SOURCE of
    not publishing, when the pipeline only knows its OWN read is old — BB may
    have published several times since. The note states our read's age, not
    an inference about the source's behaviour."""
    v = metric_vintage(_m(as_of=date(2026, 3, 1)), today=TODAY)
    assert v is not None
    assert v.freshness == "stale"
    assert "overdue" not in v.note
    assert "our latest read" in v.note


# ── event cadence keeps landmine 24's semantics ──────────────────────────────

def test_a_restamped_event_metric_has_no_vintage() -> None:
    """A standing policy rate confirmed today is current, however long it has
    been in force. Landmine 24."""
    m = _m("policy_rate_repo", label="Repo", value=9.5, as_of=TODAY, cadence="event")
    assert metric_vintage(m, today=TODAY) is None


def test_an_event_metric_whose_writer_stopped_says_last_confirmed() -> None:
    """The as_of on a standing value is a RESTAMP date, not a decision date, so
    "Mar print" would be a lie. "Last confirmed" is the only honest reading."""
    m = _m("policy_rate_repo", label="Repo", value=9.5,
           as_of=date(2026, 7, 1), cadence="event")
    v = metric_vintage(m, today=TODAY)
    assert v is not None
    assert "last confirmed" in v.note
    assert "print" not in v.note


def test_a_fallback_sourced_event_metric_is_vintaged_even_when_stamped_today() -> None:
    """bb.py stamps as_of=today on a fallback constant, so only `stale=True`
    marks it — and it must not read as confirmed-current."""
    m = _m("policy_rate_repo", label="Repo", value=9.5, as_of=TODAY,
           cadence="event", stale=True)
    v = metric_vintage(m, today=TODAY)
    assert v is not None
    assert v.freshness == "stale"


# ── the editor payload ───────────────────────────────────────────────────────

def test_vintage_payload_is_none_for_a_fresh_metric() -> None:
    assert vintage_payload(_m(as_of=date(2026, 7, 20)), today=TODAY) is None


def test_vintage_payload_carries_what_the_prompt_documents() -> None:
    p = vintage_payload(_m(), today=TODAY)
    assert p is not None
    assert set(p) == {"as_of", "age_days", "freshness", "period_label", "note"}
    assert p["as_of"] == "2026-03-01"
    assert p["period_label"] == "Mar 2026"


# ── post-editor stamping onto the published metric ───────────────────────────

class _PubMetric:
    def __init__(self, label: str) -> None:
        self.label = label
        self.held_from: date | None = None
        self.next_print: str | None = None
        self.changed = False


class _PubSection:
    def __init__(self, slug: str, metrics: list[_PubMetric]) -> None:
        self.slug = slug
        self.metrics = metrics


class _PubBrief:
    def __init__(self, sections: list[_PubSection]) -> None:
        self.sections = sections


def _v5_macro(metrics: list[Metric]) -> SectionData:
    return SectionData(id="macro", title="Macro & Inflation", metrics=metrics,
                       freshness="stale")


def test_an_old_metric_gets_its_as_of_stamped_onto_the_published_row() -> None:
    """The footer has existed since v1.2.0 and never rendered — `mark_held_overs`
    reads `section_slug` and `last_print_date` off `metric_definitions`, and
    neither column exists in production."""
    pub = _PubBrief([_PubSection("macro", [_PubMetric("REER")])])
    n = stamp_vintages(pub, [_v5_macro([_m()])], today=TODAY)

    assert n == 1
    assert pub.sections[0].metrics[0].held_from == date(2026, 3, 1)


def test_a_fresh_metric_is_not_stamped() -> None:
    pub = _PubBrief([_PubSection("macro", [_PubMetric("REER")])])
    n = stamp_vintages(pub, [_v5_macro([_m(as_of=date(2026, 7, 25))])], today=TODAY)

    assert n == 0
    assert pub.sections[0].metrics[0].held_from is None


def test_stamping_never_overwrites_mark_held_overs() -> None:
    """A metric the catalog CAN explain keeps the catalog's answer — that path
    knows the source's real last print date, which as_of only approximates."""
    already = _PubMetric("REER")
    already.held_from = date(2026, 1, 15)
    pub = _PubBrief([_PubSection("macro", [already])])
    stamp_vintages(pub, [_v5_macro([_m()])], today=TODAY)

    assert already.held_from == date(2026, 1, 15)


def test_stamping_leaves_next_print_alone() -> None:
    """This function has no honest value for `next_print`, and blanking it would
    clobber `mark_held_overs` the day the catalog is fixed — that path reads a
    real publication date and is the only thing entitled to write the field."""
    untouched = _PubMetric("REER")
    untouched.next_print = "Sep 2026"
    pub = _PubBrief([_PubSection("macro", [untouched])])
    stamp_vintages(pub, [_v5_macro([_m()])], today=TODAY)

    assert untouched.held_from == date(2026, 3, 1)
    assert untouched.next_print == "Sep 2026"


def test_a_metric_that_moved_but_is_still_old_is_stamped() -> None:
    """The first issue after a source repoint: the value changes AND is months
    old. That is exactly when the reader needs the date."""
    moved = _PubMetric("REER")
    moved.changed = True
    pub = _PubBrief([_PubSection("macro", [moved])])

    assert stamp_vintages(pub, [_v5_macro([_m()])], today=TODAY) == 1
    assert moved.held_from == date(2026, 3, 1)


def test_a_published_metric_with_no_builder_match_is_skipped() -> None:
    """The editor can invent a metric label; an unmatched row gets no vintage
    rather than a guessed one."""
    pub = _PubBrief([_PubSection("macro", [_PubMetric("Something Invented")])])
    assert stamp_vintages(pub, [_v5_macro([_m()])], today=TODAY) == 0


def test_matching_is_scoped_by_section_slug() -> None:
    """Two sections can carry the same label; a vintage must not leak across."""
    pub = _PubBrief([_PubSection("fx", [_PubMetric("REER")])])
    assert stamp_vintages(pub, [_v5_macro([_m()])], today=TODAY) == 0


# ── the editor's input, before a word is written ─────────────────────────────

def test_the_editor_input_carries_a_vintage_on_the_old_metric() -> None:
    """The half that would have stopped #184. `as_of` already reached the editor
    inside the metric dump, but a bare date carries no threshold — nothing told
    it 2026-03-01 was five months back."""
    from brief.pipeline_v6 import _to_v6_raw

    old = _m()
    fresh = _m("fx_usd_bdt", label="USD/BDT", value=123.82,
               as_of=TODAY, cadence="daily")
    raw = _to_v6_raw([_v5_macro([old, fresh])], today=TODAY)

    by_label = {m["label"]: m for m in raw[0]["metrics"]}
    assert by_label["REER"]["vintage"]["period_label"] == "Mar 2026"
    assert by_label["REER"]["vintage"]["age_days"] == 155
    # The number it got paired with is same-day — no vintage, no noise.
    assert by_label["USD/BDT"]["vintage"] is None


def test_every_editor_metric_carries_the_vintage_key() -> None:
    """Present-and-null, never absent: a missing key reads to the model as
    "unknown", a null reads as "checked, and it's current"."""
    from brief.pipeline_v6 import _to_v6_raw

    raw = _to_v6_raw([_v5_macro([_m(as_of=TODAY, cadence="daily")])], today=TODAY)
    assert "vintage" in raw[0]["metrics"][0]
