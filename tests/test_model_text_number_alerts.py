"""R2 fix H6, owner decision (n) (28 Sep 2026 BDT, option c of Q3): WARN only.

A figure the producer refused or left undated today, or any unmatched money/percent figure, that
the model writes into ANY text field of the published brief is named in the EXISTING grouped
prose-number alert (one per run). The publish always continues: the fields this fix newly scans,
and the refused-figure check everywhere, stay warn-only even under BRIEF_PROSE_VALIDATOR_STRICT=1,
while the fields that were already scanned keep exactly their STRICT hold.

Controller ruling in the same task: the model-written `brief.cover_metric` numbers (value, as_of,
next_print, held_from) never publish unless they equal the checked card the cover points to; the
cover's value is printed from that card (fix 7b's stamp), and a cover pointing at no checked card
keeps its words but no number (value "—", dates cleared). The cover is not rendered, but the
`briefs` row is public.

Fakes only: fake Editor/Sub-editor, no Supabase, no alerts sent (the alert sink is a list).
"""
from __future__ import annotations

import json
import types
import typing
from datetime import date

import pytest
from pydantic import BaseModel

from brief import alerts as alerts_module
from brief import pipeline_v6
from brief.econdelta import load_snapshot
from brief.publication_identity import PublishIdentity
from brief.v6_schema import BriefPayloadV6
from brief.validators import prose_numbers
from tests.test_producer_consumer_contract import TODAY, gathered_sections
from tests.test_shared_case_contract import (
    PUBLISHED_SECTIONS,
    cards_of,
    model_section,
    variant_run,
)

REFUSED = "98.32"  # today's Brent quote in the fixture's rejected-Brent variants
REJECTED_RUN = "rejected-brent-without-predecessor"
# SYNTHETIC: the same Brent quote arriving WITHOUT its source date, so the producer publishes it
# as an `unavailable` record (utils/observations.py: no source_as_of -> quality "unavailable",
# date_basis "unknown"). The review-rejected quote itself never reaches latest.json (the
# producer drops a rejected family before writing it), so only this shape can carry 98.32 to
# the Brief's snapshot. Value, unit and source are the fixture's; the missing date is the change.
SYNTHETIC_UNDATED_BRENT = {
    "metric_id": "brent_crude_usd_barrel", "value": 98.32, "as_of": None, "unit": "USD/barrel",
    "source": "commodity_prices", "source_url": None, "captured_at": "2026-09-24T19:45:00+00:00",
    "quality": "unavailable", "date_basis": "unknown",
    "evidence": "SYNTHETIC: commodity_prices snapshot field brent_crude_usd_barrel, no source date",
    "dependencies": [], "release_status": "unknown"}


def undated_brent_run(tmp_path):
    """The real 25 Sep run with today's Brent quote published undated (SYNTHETIC, see above)."""
    _, rows = variant_run(tmp_path, REJECTED_RUN)
    path = tmp_path / "latest.json"
    payload = json.loads(path.read_text())
    payload["observations"]["brent_crude_usd_barrel"] = SYNTHETIC_UNDATED_BRENT
    payload["data"]["brent_crude_usd_barrel"] = SYNTHETIC_UNDATED_BRENT["value"]
    path.write_text(json.dumps(payload))
    return load_snapshot(path), rows


def run(monkeypatch, snap, rows, *, brief_extra: dict | None = None, iran_extra: dict | None = None,
        wti_extra: dict | None = None, strict: bool = False):
    """run_publish on the real builders' sections with a fake Editor + Sub-editor (revise) that
    return one model brief: the bb section (corridor re-injected by code) and the Iran section
    with the WTI card. Returns (published payload or None, alerts, error or None)."""
    if strict:
        monkeypatch.setenv("BRIEF_PROSE_VALIDATOR_STRICT", "1")
    sections = pipeline_v6_sections(monkeypatch, snap, rows)
    wti = cards_of(sections)["iranwar_wti_spot"].label
    iran = {**model_section("iranwar", [{"label": wti, "value": "$92.25", "sub": "Oil spot", **(wti_extra or {})}]),
            **(iran_extra or {})}
    model = {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat(), **(brief_extra or {})},
             "sections": [model_section("bb", []), iran]}
    alerts: list[str] = []
    published: list = []
    fakes = {"_alert": alerts.append, "fetch_previous_brief": lambda: None,
             "fetch_recent_news": lambda **kw: [], "fetch_metric_definitions": list,
             "_fetch_series_summaries": lambda *a, **kw: {}, "_stamp_chart_series": lambda *a, **kw: None,
             "_call_with_retries": lambda *, label, **kw: (
                 model if label == "editor_v6" else {"verdict": "revise", "issues": [], "revised_brief": model})}
    for name, fake in fakes.items():
        monkeypatch.setattr(pipeline_v6, name, fake)
    monkeypatch.setattr(pipeline_v6, "publish_brief", lambda payload, **kw: published.append(payload) or "local")
    try:
        pipeline_v6.run_publish(sections, TODAY, expected_identity=PublishIdentity(1, TODAY))
        error = None
    except pipeline_v6.V6PublishError as exc:
        error = exc
    return (published[0] if published else None), alerts, error


def pipeline_v6_sections(monkeypatch, snap, rows):
    return _published_only(gathered_sections(monkeypatch, snap, rows))


def _published_only(gathered):
    """The published sections, keeping the gathered snapshot (`GatheredSections.snapshot`)."""
    kept = type(gathered)(s for s in gathered if s.id in PUBLISHED_SECTIONS)
    kept.snapshot = gathered.snapshot
    return kept


def wti_label(monkeypatch, snap, rows) -> str:
    return cards_of(pipeline_v6_sections(monkeypatch, snap, rows))["iranwar_wti_spot"].label


def gate_alerts(alerts: list[str]) -> list[str]:
    return [a for a in alerts if "prose-number gate" in a]


# Where the model can write text, and the alert location that must name it. The cover label is
# prefixed with the WTI card's own label so the cover stays bound to a checked card.
def placements(figure: str, wti: str) -> dict[str, tuple[dict, dict, dict, str]]:
    """{name: (brief_extra, iran_extra, wti_extra, alert location)}."""
    pill = {"tone": "neu"}
    return {
        # Newly scanned (warn-only even under STRICT).
        "brief.frame": ({"frame": f"oil at {figure}"}, {}, {}, "brief.frame"),
        "brief.cover_metric.label": ({"cover_metric": {"label": f"{wti} · {figure}", "value": "$92.25",
                                                       "section_slug": "iran"}}, {}, {},
                                     "brief.cover_metric.label"),
        "brief.cover_metric.sub": ({"cover_metric": {"label": wti, "value": "$92.25", "section_slug": "iran",
                                                     "sub": f"Brent {figure} on 23 Sep"}}, {}, {},
                                   "brief.cover_metric.sub"),
        "section.title": ({}, {"title": f"Oil at {figure}"}, {}, "iran.title"),
        "unbound pill value": ({}, {"summary_pills": [{"key": "Oil", "value": figure, **pill}]}, {},
                               "iran.summary_pills[0].value"),
        "unbound pill key": ({}, {"summary_pills": [{"key": f"Crude {figure}", "value": "up", **pill}]}, {},
                             "iran.summary_pills[0].key"),
        "news.headline": ({}, {"news": [{"headline": f"Brent hits {figure}", "detail": "Oil."}]}, {},
                          "iran.news[0].headline"),
        "news.detail": ({}, {"news": [{"headline": "Oil", "detail": f"Brent hit {figure} on 23 Sep."}]}, {},
                        "iran.news[0].detail"),
        "news.source": ({}, {"news": [{"headline": "Oil", "source": f"Wire {figure}"}]}, {},
                        "iran.news[0].source"),
        # Already scanned for money/percent figures (their STRICT behaviour is unchanged).
        "brief.todays_call": ({"todays_call": f"Brent printed {figure} on 23 Sep."}, {}, {},
                              "brief.todays_call"),
        "section.tldr": ({}, {"tldr": f"Brent at {figure}."}, {}, "iran.tldr"),
        "section.verdict": ({}, {"verdict": f"Brent at {figure}."}, {}, "iran.verdict"),
        "section.analysis": ({}, {"analysis": f"Brent jumped to {figure} a barrel."}, {}, "iran.analysis"),
        "card sub": ({}, {}, {"sub": f"Brent at {figure} today"}, "iran.metrics[0].sub"),
        "banker_read.verdict": ({}, {"banker_read": {"verdict": f"Brent at {figure} squeezes the import bill."}},
                                {}, "iran.banker_read.verdict"),
        "banker_read.watch": ({}, {"banker_read": {"verdict": "Oil squeezes the import bill.",
                                                   "watch": [f"Brent {figure}"]}}, {},
                              "iran.banker_read.watch[0]"),
        "chart_read.context": ({}, {"chart_read": {"signal": "Oil flat.", "context": f"Brent {figure}.",
                                                   "implication": "Import bill."}}, {},
                               "iran.chart_read.context"),
    }


NEWLY_SCANNED = ("brief.frame", "brief.cover_metric.label", "brief.cover_metric.sub", "section.title",
                 "unbound pill value", "unbound pill key", "news.headline", "news.detail", "news.source")
ALL_PLACEMENTS = tuple(placements("x", "y"))


# ── (1)+(2): each field, '$98.32' or a bare '98.32' -> ONE grouped WARN alert, publish proceeds ──

@pytest.mark.parametrize("form", ["$" + REFUSED, REFUSED])
@pytest.mark.parametrize("field", ALL_PLACEMENTS)
def test_a_refused_figure_in_any_model_text_field_is_named_in_one_warn_alert_and_still_publishes(
        tmp_path, monkeypatch, field, form):
    snap, rows = undated_brent_run(tmp_path)
    brief_extra, iran_extra, wti_extra, location = placements(form, wti_label(monkeypatch, snap, rows))[field]
    published, alerts, error = run(monkeypatch, snap, rows, brief_extra=brief_extra, iran_extra=iran_extra,
                                   wti_extra=wti_extra)
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    assert f"{location}: " in alert
    assert REFUSED in alert.split(f"{location}: ", 1)[1].splitlines()[0]


@pytest.mark.parametrize("field", NEWLY_SCANNED)
def test_an_unmatched_money_figure_in_a_newly_scanned_field_warns_in_the_real_rejected_brent_run(
        tmp_path, monkeypatch, field):
    """The real rejected-Brent run (no Brent record at all): '$98.32' matches no builder value."""
    snap, rows = variant_run(tmp_path, REJECTED_RUN)
    brief_extra, iran_extra, wti_extra, location = placements("$" + REFUSED, wti_label(monkeypatch, snap, rows))[field]
    published, alerts, error = run(monkeypatch, snap, rows, brief_extra=brief_extra, iran_extra=iran_extra,
                                   wti_extra=wti_extra)
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    assert f"{location}: '${REFUSED}'" in alert


@pytest.mark.parametrize("field", NEWLY_SCANNED)
def test_a_newly_scanned_field_stays_warn_only_under_strict(tmp_path, monkeypatch, field):
    snap, rows = variant_run(tmp_path, REJECTED_RUN)
    brief_extra, iran_extra, wti_extra, location = placements("$" + REFUSED, wti_label(monkeypatch, snap, rows))[field]
    published, alerts, error = run(monkeypatch, snap, rows, brief_extra=brief_extra, iran_extra=iran_extra,
                                   wti_extra=wti_extra, strict=True)
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    assert location in alert


@pytest.mark.parametrize("field", ALL_PLACEMENTS)
def test_a_bare_refused_figure_never_holds_the_publish_even_under_strict(tmp_path, monkeypatch, field):
    snap, rows = undated_brent_run(tmp_path)
    brief_extra, iran_extra, wti_extra, location = placements(REFUSED, wti_label(monkeypatch, snap, rows))[field]
    published, alerts, error = run(monkeypatch, snap, rows, brief_extra=brief_extra, iran_extra=iran_extra,
                                   wti_extra=wti_extra, strict=True)
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    assert location in alert


@pytest.mark.parametrize("field", ["section.analysis", "card sub", "brief.todays_call", "chart_read.context"])
def test_strict_still_holds_an_unmatched_money_figure_in_an_already_scanned_field(tmp_path, monkeypatch, field):
    snap, rows = variant_run(tmp_path, REJECTED_RUN)
    brief_extra, iran_extra, wti_extra, _ = placements("$" + REFUSED, wti_label(monkeypatch, snap, rows))[field]
    published, _, error = run(monkeypatch, snap, rows, brief_extra=brief_extra, iran_extra=iran_extra,
                              wti_extra=wti_extra, strict=True)
    assert isinstance(error, pipeline_v6.ProseNumberGateError) and published is None


def test_clean_model_text_raises_no_number_alert(tmp_path, monkeypatch):
    """Years, counts, dates and the day's own checked figures in the newly scanned fields are no
    alert; neither is a bound pill printed from its card."""
    snap, rows = undated_brent_run(tmp_path)
    wti = wti_label(monkeypatch, snap, rows)
    published, alerts, error = run(
        monkeypatch, snap, rows,
        brief_extra={"frame": "external-shock", "todays_call": "Oil held steady into 2026's last quarter.",
                     "cover_metric": {"label": wti, "value": "$92.25", "section_slug": "iran",
                                      "sub": "WTI at $92.25, 3 sessions flat"}},
        iran_extra={"title": "Iran War & Oil", "analysis": "WTI held at $92.25 across 12 sessions.",
                    "summary_pills": [{"key": "WTI", "value": "$91"}, {"key": "Oil", "value": "$92.25"},
                                      {"key": "Tankers", "value": "12"}],
                    "news": [{"headline": "OPEC+ meets on 30 Sep 2026", "detail": "Talks in 2026 on 3 cuts.",
                              "source": "Reuters"}]})
    assert error is None and published is not None
    assert gate_alerts(alerts) == []


def test_several_model_text_fields_share_one_alert(tmp_path, monkeypatch):
    snap, rows = undated_brent_run(tmp_path)
    published, alerts, error = run(
        monkeypatch, snap, rows, brief_extra={"frame": f"oil {REFUSED}"},
        iran_extra={"title": f"Oil {REFUSED}", "news": [{"headline": f"Brent ${REFUSED}"}],
                    "summary_pills": [{"key": "Oil", "value": f"${REFUSED}"}]})
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    for location in ("brief.frame", "iran.title", "iran.news[0].headline", "iran.summary_pills[0].value"):
        assert location in alert


# SYNTHETIC noise: 30 dollar figures no builder produced, so the existing lede check (WARN) writes
# ~30 lines before any refused-figure line — the size of a real grouped alert (R2 H6 review r0:
# 4.3k-14.1k chars on issues #199-#205 and 25 Sep), well past what Discord is sent.
NOISY_ANALYSIS = "Synthetic noise: " + ", ".join(f"${7000 + i}.{i + 10}" for i in range(30)) + "."


@pytest.mark.parametrize("brief_extra,iran_extra,location", [
    ({}, {"news": [{"headline": f"Brent hits {REFUSED}", "detail": "Oil."}]}, "iran.news[0].headline"),
    ({"frame": f"oil at {REFUSED}"}, {}, "brief.frame"),
])
def test_a_refused_figure_is_visible_in_the_part_of_a_long_alert_discord_receives(
        tmp_path, monkeypatch, brief_extra, iran_extra, location):
    """The refused-figure line is the one signal H6 adds; on a real-sized day the grouped alert is
    far longer than the 1990 chars `alerts.send_discord_alert` posts. The owner must still see the
    refused figure and its field in Discord, not only in the journal."""
    snap, rows = undated_brent_run(tmp_path)
    published, alerts, error = run(monkeypatch, snap, rows, brief_extra=brief_extra,
                                   iran_extra={"analysis": NOISY_ANALYSIS, **iran_extra})
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    assert len(alert) > alerts_module._MAX_CONTENT            # the noise really overflows Discord's cut
    sent = alert[:alerts_module._MAX_CONTENT]                  # exactly what send_discord_alert posts
    refused_lines = [line for line in sent.splitlines() if f"{location}: '{REFUSED}'" in line]
    assert len(refused_lines) == 1 and prose_numbers.REFUSED_FIGURE_KIND in refused_lines[0]
    assert sum(f"{location}: '{REFUSED}'" in line for line in alert.splitlines()) == 1   # listed once
    assert alert.startswith("WARN: The Brief prose-number gate — ")                    # same one alert


@pytest.mark.parametrize("headlines,listed,not_listed", [(10, 10, 0), (11, 10, 1), (14, 10, 4)],
                         ids=["ten-all-listed", "eleven-one-counted", "fourteen-four-counted"])
def test_a_long_refused_group_lists_ten_and_counts_the_rest_inside_what_discord_receives(
        tmp_path, monkeypatch, headlines, listed, not_listed):
    """Beyond ~12 refused lines, Discord's 1990-char cut used to drop the later ones silently. The
    group lists at most 10 and ends with ONE line saying how many more were not listed, all inside
    the part Discord receives; the header and group counts still cover every figure. Still ONE
    grouped alert (owner decisions (k), (n)). SYNTHETIC: the undated Brent quote in N headlines."""
    snap, rows = undated_brent_run(tmp_path)
    news = [{"headline": f"Brent hits {REFUSED}", "detail": "Oil."} for _ in range(headlines)]
    published, alerts, error = run(monkeypatch, snap, rows,
                                   iran_extra={"analysis": NOISY_ANALYSIS, "news": news})
    assert error is None and published is not None
    [alert] = gate_alerts(alerts)
    lines = alert.splitlines()
    refused_lines = [line for line in lines if prose_numbers.REFUSED_FIGURE_KIND in line]
    assert len(refused_lines) == listed
    assert f"  [refused or undated today — {headlines} figure(s)]" in lines   # group count: every figure
    other_lines = [line for line in lines[1:] if line.startswith("    ") and line not in refused_lines]
    more = [line for line in lines if "not listed" in line]
    assert len(more) == (1 if not_listed else 0)
    counted = len(other_lines) - len(more) + headlines                         # every warning, listed or not
    assert lines[0].startswith(f"WARN: The Brief prose-number gate — {counted} figure(s) across ")
    if not_listed:
        assert more == [(f"    … and {not_listed} more refused or undated figure(s) not listed here "
                         "(each is in the brief log)")]
        assert lines.index(more[0]) == lines.index(refused_lines[-1]) + 1      # closes the refused group
        assert more[0] in alert[:alerts_module._MAX_CONTENT].splitlines()      # Discord receives it


# The producer's own refused FX record on the 25 Sep run (EconDelta latest.json, copied from the
# fix2 producer snapshot): its reason makes the longest real refused line, ~185 chars.
PRODUCER_UNAVAILABLE_FX = {
    "metric_id": "usd_bdt_exchange_rate", "value": 123.22, "as_of": "2026-09-25", "unit": "BDT",
    "source": "bb_forex", "source_url": "https://www.bb.org.bd/en/index.php/econdata/exchangerate",
    "captured_at": "2026-09-24T19:35:00+00:00", "quality": "unavailable", "date_basis": "observation",
    "evidence": "bb_forex snapshot field usd_bdt_mid", "dependencies": ["usd_bdt_mid"],
    "release_status": "unknown"}


def _fx_quoted_in_banker_reads(fields: int) -> list[prose_numbers.NumberWarning]:
    """The real refused-figure check on a model brief quoting the unavailable USD/BDT rate in
    `fields` banking/macro banker-read and chart-read fields. SYNTHETIC: the prose placement."""
    figure = prose_numbers.RefusedFigure(
        metric_id=PRODUCER_UNAVAILABLE_FX["metric_id"], value=PRODUCER_UNAVAILABLE_FX["value"],
        reason=pipeline_v6._refusal_reason(PRODUCER_UNAVAILABLE_FX))
    quote = "The dollar at 123.22 taka."
    banking = {**model_section("banking", []),
               "banker_read": {"verdict": quote, "watch": [quote] * 4, "risk": [quote] * 4},
               "chart_read": {"signal": quote, "context": quote, "implication": quote}}
    macro = {**model_section("macro", []), "banker_read": {"verdict": quote, "watch": [quote] * 2}}
    final_brief = BriefPayloadV6.model_validate(
        {"brief": {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat()}, "sections": [banking, macro]})
    warnings = prose_numbers.check_refused_figures(final_brief, [], (figure,))
    assert len(warnings) == 15                                  # the fixture really carries 15 fields
    return warnings[:fields]


@pytest.mark.parametrize("fields", [10, 11, 15])
def test_every_listed_refused_line_and_the_more_line_arrive_whole_in_discord_on_the_longest_real_reason(
        fields):
    """Controller fix C1 round 1: the 10-line cap alone assumed ~150-char lines; the producer's
    real 'unavailable (as of …)' FX reason makes ~185-char lines, and Discord's 1990-char cut then
    dropped the '… and N more' line (or the last listed line) silently. Whatever the line length,
    every refused line listed and the closing count line must arrive WHOLE in the part Discord
    receives, and listed + counted must cover every refused figure. Still ONE alert."""
    warnings = _fx_quoted_in_banker_reads(fields)
    alert = pipeline_v6._format_prose_number_alert(warnings)
    lines = alert.splitlines()
    received = alert[:alerts_module._MAX_CONTENT].splitlines()
    listed = [line for line in lines if prose_numbers.REFUSED_FIGURE_KIND in line]
    assert listed == [f"    {w.describe()}" for w in warnings[:len(listed)]]   # the first ones, in order
    assert 1 <= len(listed) <= 10 and all(line in received for line in listed)
    more = [line for line in lines if "not listed" in line]
    not_listed = fields - len(listed)
    assert more == ([(f"    … and {not_listed} more refused or undated figure(s) not listed here "
                      "(each is in the brief log)")] if not_listed else [])
    assert all(line in received for line in more)                          # arrives whole
    assert lines[0] == f"WARN: The Brief prose-number gate — {fields} figure(s) across 2 section(s):"
    assert f"  [refused or undated today — {fields} figure(s)]" in received


# ── (2) the matching rule, on the check itself ──

def test_the_producers_refused_and_undated_records_are_the_only_figures_matched(tmp_path):
    """Refused = a record the reader does not accept today: the undated NBR family (real fixture
    variant). The held Brent predecessor and every verified record are accepted, never refused."""
    snap, _ = variant_run(tmp_path, "missing-period-tax-revenue")
    refused = {f.metric_id: f.value for f in pipeline_v6._refused_figures(snap, TODAY)}
    assert refused == {"tax_revenue": 415473.0, "fiscal_nbr_collected_trn": 4.15, "nbr_fytd_collected_cr": 415473.0}
    (tmp_path / "held").mkdir()
    held, _ = variant_run(tmp_path / "held", "rejected-brent-with-dated-predecessor")
    assert pipeline_v6._refused_figures(held, TODAY) == ()


@pytest.mark.parametrize("value,text,matches", [
    (98.32, "98.32", True), (98.32, "$98.32/bbl", True), (98.32, "98.320", True), (98.32, "−98.32", True),
    (98.32, "98.3", False), (98.32, "98", False), (98.32, "9832", False), (98.32, "198.32", False),
    (98.31999969482422, "98.32", True),               # float32 widening: the quote as displayed
    (8.3198, "8.31", True), (8.3198, "8.32", True), (8.3198, "8.3198", True), (8.3198, "8.3", False),
    (415473.0, "415,473", True), (415473.0, "4,15,473", True), (415473.0, "415473.5", False),
    (4.15, "Tk 4.15trn", True), (4.15, "4.1", False), (4.15, "4", False),
    (2026.0, "2026", False),                          # a year is never matched
    (12.0, "12", False), (9.5, "9.5", False),          # fewer than 3 significant digits: never matched
])
def test_a_refused_figure_is_matched_at_display_precision_only(value, text, matches):
    figure = prose_numbers.RefusedFigure(metric_id="x", value=value, reason="SYNTHETIC")
    found = prose_numbers.refused_figure_tokens(f"say {text} now", [figure])
    assert bool(found) is matches


def test_a_refused_value_equal_to_a_checked_builder_figure_is_not_flagged():
    """The card may print the same number from its dated history (owner decision (d)); prose
    quoting that checked figure is no refused-figure alert."""
    figure = prose_numbers.RefusedFigure(metric_id="fiscal_nbr_collected_trn", value=4.15, reason="undated")
    brief = BriefPayloadV6.model_validate({
        "brief": {"issue_no": 1, "volume": 1, "brief_date": "2026-09-25"},
        "sections": [{"slug": "fiscal", "ord": 9, "title": "Fiscal", "group_key": "policy",
                      "analysis": "NBR collected Tk 4.15trn."}]})
    raw = [{"slug": "fiscal", "metrics": [{"id": "fiscal_nbr_collected_trn", "label": "NBR", "value": 4.15,
                                           "unit": "BDT trn"}]}]
    assert prose_numbers.check_refused_figures(brief, raw, [figure]) == []
    assert prose_numbers.check_refused_figures(brief, [{"slug": "fiscal", "metrics": []}], [figure]) != []


# ── every model-written text field of the published object is classified, and scanned ──

def _text_paths(model: type, prefix: str) -> set[str]:
    paths: set[str] = set()
    for name, info in model.model_fields.items():
        inner = info.annotation
        if typing.get_origin(inner) in (typing.Union, types.UnionType):  # Optional[X] -> X
            inner = next(a for a in typing.get_args(inner) if a is not type(None))
        list_inner = typing.get_args(inner)[0] if typing.get_origin(inner) is list else None
        target = list_inner if list_inner is not None else inner
        path = f"{prefix}{name}" + ("[]" if list_inner is not None else "")
        if isinstance(target, type) and issubclass(target, BaseModel):
            paths |= _text_paths(target, path + ".")
        elif target is str:
            paths.add(path)
    return paths


def test_every_text_field_of_the_published_schema_is_either_scanned_or_shown_not_to_carry_model_figures():
    """A new model-written text field must be added to the scan (or explicitly shown to be
    printed by code or metadata) — never silently left unscanned."""
    schema = _text_paths(BriefPayloadV6, "")
    scanned = set(prose_numbers.SCANNED_TEXT_PATHS) | set(prose_numbers.WARN_ONLY_TEXT_PATHS)
    assert scanned.isdisjoint(prose_numbers.NOT_SCANNED_TEXT_PATHS)
    assert scanned | set(prose_numbers.NOT_SCANNED_TEXT_PATHS) == schema
    assert {"brief.frame", "brief.cover_metric.label", "brief.cover_metric.sub", "sections[].title",
            "sections[].summary_pills[].key", "sections[].summary_pills[].value", "sections[].news[].headline",
            "sections[].news[].detail", "sections[].news[].source"} <= set(prose_numbers.WARN_ONLY_TEXT_PATHS)


# ── (3) controller ruling: brief.cover_metric numbers ──

def published_card(published, label: str):
    return next(m for s in published.sections for m in s.metrics if m.label == label)


def test_a_cover_with_model_numbers_is_printed_from_the_checked_card_it_points_to(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, REJECTED_RUN)
    wti = wti_label(monkeypatch, snap, rows)
    published, _, error = run(monkeypatch, snap, rows, brief_extra={"cover_metric": {
        "label": wti.upper(), "value": f"${REFUSED}/bbl", "section_slug": "iran", "as_of": "2026-09-24",
        "next_print": f"${REFUSED} on 23 Sep", "held_from": "2026-09-22"}})
    assert error is None and published is not None
    cover, card = published.brief.cover_metric, published_card(published, wti)
    assert (cover.value, cover.held_from, cover.next_print) == (card.value, card.held_from, card.next_print)
    assert cover.as_of is None  # the model's date is not the card's observation date (23 Sep)
    assert REFUSED not in cover.model_dump_json()


def test_a_cover_equal_to_its_checked_card_is_kept(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, REJECTED_RUN)
    wti_card = cards_of(pipeline_v6_sections(monkeypatch, snap, rows))["iranwar_wti_spot"]
    printed = pipeline_v6._format_metric_value(wti_card.value, wti_card.unit, wti_card.id)
    cover = {"label": wti_card.label, "value": printed, "section_slug": "iran",
             "as_of": wti_card.as_of.isoformat(), "sub": "Oil spot", "tone": "neu"}
    published, _, error = run(monkeypatch, snap, rows, brief_extra={"cover_metric": cover})
    assert error is None
    assert published.brief.cover_metric.model_dump(mode="json") == {
        **cover, "held_from": None, "next_print": None}


@pytest.mark.parametrize("cover", [
    {"label": "BRENT", "value": f"${REFUSED}", "section_slug": "iran"},       # no Brent card today
    {"label": "WTI spot", "value": f"${REFUSED}", "section_slug": "macro"},   # a section not published
    {"label": "WTI spot", "value": f"${REFUSED}"},                            # no section named, no hero
])
def test_a_cover_pointing_at_no_checked_card_keeps_no_model_number(tmp_path, monkeypatch, cover):
    snap, rows = variant_run(tmp_path, REJECTED_RUN)
    dated = {**cover, "as_of": "2026-09-23", "next_print": f"${REFUSED} on 23 Sep", "held_from": "2026-09-22"}
    published, _, error = run(monkeypatch, snap, rows, brief_extra={"cover_metric": dated})
    assert error is None and published is not None
    out = published.brief.cover_metric
    assert (out.label, out.value, out.as_of, out.next_print, out.held_from) == (cover["label"], "—", None, None, None)
    assert REFUSED not in out.model_dump_json()


def test_a_cover_on_a_held_card_carries_the_cards_held_date(tmp_path, monkeypatch):
    snap, rows = variant_run(tmp_path, "rejected-brent-with-dated-predecessor")
    cards = cards_of(pipeline_v6_sections(monkeypatch, snap, rows))
    brent = cards["iranwar_brent_spot"].label
    metrics = [{"label": cards["iranwar_wti_spot"].label, "value": "$92.25"},
               {"label": brent, "value": f"${REFUSED}", "held_from": None}]
    published, _, error = run(monkeypatch, snap, rows, iran_extra={"metrics": metrics}, brief_extra={
        "cover_metric": {"label": brent, "value": f"${REFUSED}", "section_slug": "iran", "held_from": None}})
    assert error is None
    cover, card = published.brief.cover_metric, published_card(published, brent)
    assert (cover.value, cover.held_from) == (card.value, date(2026, 9, 22))
