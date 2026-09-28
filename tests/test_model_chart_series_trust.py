"""R2 fix #6 — the model cannot supply chart data; cards agree with their own chart.

Business rules pinned here (fake models only, no network):

1. Chart points (`series`), chart annotations (`notes`) and DS30 movers
   (`movers`) are machine-stamped after the model runs. The Editor prompt says
   `series`/`notes` are ALWAYS empty in its output, and the model is never given
   the points or the movers at all. So nothing the Editor or the Sub-editor puts
   in those fields may reach the published brief — whether stamping succeeds,
   a fetch raises, or Supabase credentials are missing.
2. A failed or skipped chart stamp does not hold the brief (existing policy in
   `run_publish`: "degraded charts must not block a publish"). The section
   ships with an empty chart and a logged reason naming it.
3. For the unambiguous same-concept, same-period card/chart pairs, a card's
   builder value must equal its own chart's point for the card's date when that
   point exists. A mismatch is logged + alerted (WARN, like the sibling
   as_of-vs-series gate) and neither number is rewritten.

All values below are synthetic test inputs, not production readings.
"""
from __future__ import annotations

import logging
import socket
from datetime import date
from typing import Any

import pytest

from brief import chart_series_fetcher, pipeline_v6
from brief.publication_identity import PublishIdentity
from brief.schema import Metric, SectionData
from brief.v6_schema import (
    BriefPayloadV6,
    BriefV6,
    MetricV6,
    SectionV6,
    SeriesPointV6,
)

TODAY = date(2026, 9, 21)  # a Monday: the weekday editor prompt, not Friday's wrap
SUPABASE_URL = "https://fake.invalid"
SERVICE_KEY = "fake-service-key"

# What a model might try to smuggle into the machine-stamped chart fields.
INVENTED_POINT = {"key": "exports_usd_mn_monthly", "ts": "2026-08-31", "value": 9999.0}
INVENTED_NOTE = {"series_key": "dsex", "ts": "2026-09-20", "label": "Model-invented crash"}
INVENTED_MOVER = {"ticker": "INVENTED", "price": 1.0, "return_pct": 99.0}

# What the deterministic fetchers return in these tests.
STAMPED_FX = SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-06-30", value=4202.69)
STAMPED_DSEX = SeriesPointV6(key="dsex", ts="2026-09-20", value=5540.32)


@pytest.fixture(autouse=True)
def _refuse_network(monkeypatch: pytest.MonkeyPatch):
    """Hermetic: any socket connect or DNS lookup fails the test."""
    attempts: list[str] = []

    def refuse_connect(self: socket.socket, address: object) -> None:
        attempts.append(f"connect({address!r})")
        raise OSError(f"test refused outbound connect to {address!r}")

    def refuse_lookup(host: object, *args: object, **kwargs: object) -> None:
        attempts.append(f"getaddrinfo({host!r})")
        raise OSError(f"test refused DNS lookup of {host!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse_connect)
    monkeypatch.setattr(socket, "getaddrinfo", refuse_lookup)
    yield
    if attempts:
        pytest.fail("outbound network attempted: " + ", ".join(sorted(set(attempts))))


# ─── fakes ─────────────────────────────────────────────────────────────


def _raise(*_a: Any, **_k: Any) -> Any:
    raise RuntimeError("simulated chart fetch failure")


def _fake_fetchers(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> None:
    """Every chart fetcher faked; the defaults stamp STAMPED_FX / STAMPED_DSEX."""
    fakes: dict[str, Any] = {
        "fetch_dsex": lambda **_k: ([STAMPED_DSEX], []),
        "fetch_dse_movers": lambda **_k: None,  # freshness gate hid the movers
        "fetch_brent": lambda **_k: [],
        "fetch_money_market": lambda **_k: [],
        "fetch_fx_balance_monthly": lambda *_a, **_k: {STAMPED_FX.key: [STAMPED_FX]},
        "fetch_reserves_monthly": lambda *_a, **_k: {},
        "fetch_yield_ladder_monthly": lambda *_a, **_k: {},
        "fetch_yield_ladder_last_auction": lambda *_a, **_k: None,
        "fetch_macro_cpi_series": lambda *_a, **_k: {},
        "fetch_remit_monthly": lambda *_a, **_k: {},
        "fetch_fiscal_monthly": lambda *_a, **_k: {},
    }
    fakes.update(overrides)
    for name, fake in fakes.items():
        monkeypatch.setattr(chart_series_fetcher, name, fake)


def _section_json(slug: str, ord_v6: int, group: str, **extra: Any) -> dict[str, Any]:
    return {"slug": slug, "ord": ord_v6, "title": slug.upper(), "group_key": group,
            "weight": 1, **extra}


def _model_chart_payload() -> dict[str, Any]:
    """Machine-owned fields a model filled in anyway."""
    return {"series": [INVENTED_POINT], "notes": [INVENTED_NOTE], "movers": [INVENTED_MOVER]}


def _v5_sections() -> list[SectionData]:
    return [
        SectionData(id="headlines", title="Headlines", metrics=[], freshness="fresh"),
        SectionData(id="fx", title="FX", metrics=[], freshness="fresh"),
        SectionData(id="dse", title="DSE", metrics=[], freshness="fresh"),
    ]


def _model_sections(*, invented: bool) -> list[dict[str, Any]]:
    extra = _model_chart_payload() if invented else {}
    return [
        _section_json("headlines", 2, "overview", **extra),
        _section_json("fx", 5, "markets", **extra),
        _section_json("dse", 6, "markets", **extra),
    ]


def _run_publish(
    monkeypatch: pytest.MonkeyPatch,
    *,
    v5_sections: list[SectionData],
    editor_sections: list[dict[str, Any]],
    revised_sections: list[dict[str, Any]] | None = None,
    credentials: bool = True,
) -> tuple[BriefPayloadV6, list[str]]:
    """Drive the real run_publish with fake Editor/Sub-editor and no I/O."""
    if credentials:
        monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    else:
        for var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(pipeline_v6, "fetch_previous_brief", lambda: None)
    monkeypatch.setattr(pipeline_v6, "fetch_recent_news", lambda n_issues=5: [])
    monkeypatch.setattr(pipeline_v6, "fetch_metric_definitions", list)
    monkeypatch.setattr(pipeline_v6, "_fetch_series_summaries", lambda **_k: {})
    alerts: list[str] = []
    monkeypatch.setattr(pipeline_v6, "_alert", alerts.append)

    brief = {"issue_no": 1, "volume": 1, "brief_date": TODAY.isoformat(), "status": "published"}
    if revised_sections is None:
        review: dict[str, Any] = {"verdict": "pass", "issues": []}
    else:
        review = {
            "verdict": "revise",
            "issues": [{"section": "fx", "field": "verdict", "severity": "warn",
                        "problem": "tightened the section verdict wording"}],
            "revised_brief": {"brief": brief, "sections": revised_sections},
        }

    def fake_call(*, label: str, **_: Any) -> dict[str, Any]:
        if label == "editor_v6":
            return {"brief": brief, "sections": editor_sections}
        if label == "subeditor_v6":
            return review
        raise AssertionError(f"unexpected model call: {label}")

    monkeypatch.setattr(pipeline_v6, "_call_with_retries", fake_call)
    published: list[BriefPayloadV6] = []
    monkeypatch.setattr(
        pipeline_v6, "publish_brief",
        lambda payload, *, expected_identity: published.append(payload) or "fake-uuid",
    )
    result = pipeline_v6.run_publish(
        v5_sections, TODAY, expected_identity=PublishIdentity(1, TODAY),
    )
    assert result == "fake-uuid", "a chart problem must not hold the brief"
    assert len(published) == 1
    return published[0], alerts


def _by_slug(brief: BriefPayloadV6) -> dict[str, SectionV6]:
    return {s.slug: s for s in brief.sections}


def _assert_no_model_chart_data(brief: BriefPayloadV6) -> None:
    for section in brief.sections:
        values = {p.value for p in section.series}
        assert INVENTED_POINT["value"] not in values, f"{section.slug}: model point published"
        labels = {n.label for n in section.notes}
        assert INVENTED_NOTE["label"] not in labels, f"{section.slug}: model note published"
        tickers = {m.ticker for m in (section.movers or [])}
        assert INVENTED_MOVER["ticker"] not in tickers, f"{section.slug}: model movers published"


# ─── rule 1+2: model chart data never publishes ────────────────────────


@pytest.mark.parametrize("stage", ["editor", "subeditor_revise"])
def test_model_supplied_chart_data_never_reaches_the_published_brief(
    monkeypatch: pytest.MonkeyPatch, stage: str,
) -> None:
    """Invented points/notes/movers from either model call are dropped; only the
    deterministic fetchers' output is published, unchanged."""
    _fake_fetchers(monkeypatch)
    if stage == "editor":
        brief, _ = _run_publish(monkeypatch, v5_sections=_v5_sections(),
                                editor_sections=_model_sections(invented=True))
    else:
        brief, _ = _run_publish(monkeypatch, v5_sections=_v5_sections(),
                                editor_sections=_model_sections(invented=False),
                                revised_sections=_model_sections(invented=True))

    _assert_no_model_chart_data(brief)
    sections = _by_slug(brief)
    # Normal stamping is unchanged: exactly the fetchers' points, nothing else.
    assert sections["fx"].series == [STAMPED_FX]
    assert sections["dse"].series == [STAMPED_DSEX]
    assert sections["dse"].movers is None
    # A chartless section keeps no chart at all.
    assert sections["headlines"].series == []
    assert sections["headlines"].notes == []
    assert sections["headlines"].movers is None


def test_failed_chart_fetch_ships_an_empty_chart_with_a_logged_reason(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """A raising fetcher leaves no model points behind, names the chartless
    section in the log, and does not hold the brief."""
    _fake_fetchers(monkeypatch, fetch_fx_balance_monthly=_raise, fetch_dsex=_raise)
    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        brief, _ = _run_publish(monkeypatch, v5_sections=_v5_sections(),
                                editor_sections=_model_sections(invented=True))

    _assert_no_model_chart_data(brief)
    sections = _by_slug(brief)
    for slug in ("fx", "dse"):
        assert sections[slug].series == []
        assert sections[slug].notes == []
        assert sections[slug].movers is None
    reasons = [r.getMessage() for r in caplog.records if "no chart series" in r.getMessage()]
    assert any("fx" in m for m in reasons), reasons
    assert any("dse" in m for m in reasons), reasons


def test_missing_credentials_ship_empty_charts_with_a_logged_reason(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """No Supabase credentials: nothing is stamped, so nothing the model wrote
    may stand in for the chart; the log says which sections ship chartless."""
    _fake_fetchers(monkeypatch, **{name: _raise for name in (
        "fetch_dsex", "fetch_fx_balance_monthly", "fetch_dse_movers")})
    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        brief, _ = _run_publish(monkeypatch, v5_sections=_v5_sections(),
                                editor_sections=_model_sections(invented=True),
                                credentials=False)

    _assert_no_model_chart_data(brief)
    for section in brief.sections:
        assert section.series == [] and section.notes == [] and section.movers is None
    reasons = [r.getMessage() for r in caplog.records if "no chart series" in r.getMessage()]
    assert any("fx" in m and "dse" in m and "credentials" in m.lower() for m in reasons), reasons


def test_stamp_helper_itself_never_keeps_a_preexisting_series_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defence in depth for any caller of `_stamp_chart_series`: a section that
    arrives with points and whose fetch raises leaves with none."""
    _fake_fetchers(monkeypatch, fetch_fx_balance_monthly=_raise, fetch_dsex=_raise)
    brief = BriefPayloadV6(
        brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY),
        sections=[SectionV6.model_validate(s) for s in _model_sections(invented=True)],
    )
    pipeline_v6._stamp_chart_series(
        brief, today=TODAY, http=object(),  # never used: every fetcher is faked
        supabase_url=SUPABASE_URL, service_key=SERVICE_KEY,
    )
    _assert_no_model_chart_data(brief)
    assert all(s.series == [] for s in brief.sections)


# ─── rule 3: a card agrees with its own chart point for its own date ────
# (slug, card id, card label, card unit, card value, card date,
#  chart key, chart value that AGREES, chart value that DISAGREES)
_PAIRS: list[tuple[str, str, str, str, float, str, str, float, float]] = [
    ("macro", "cpi_12m_avg_monthly", "CPI 12m Avg", "%", 8.49, "2026-07-31",
     "cpi_12m_avg_monthly", 8.49, 8.66),
    ("macro", "cpi_p2p_food_monthly", "CPI Food (P-to-P)", "%", 7.56, "2026-07-31",
     "cpi_p2p_food_monthly", 7.56, 7.16),
    ("macro", "cpi_p2p_nonfood_monthly", "CPI Non-Food (P-to-P)", "%", 8.9, "2026-07-31",
     "cpi_p2p_nonfood_monthly", 8.9, 9.1),
    # Card is bn USD rounded to 2dp (fx.py); the chart plots the same official
    # EPB row in mn USD.
    ("fx", "fx_monthly_exports", "Monthly Exports", "bn USD", 4.2, "2026-06-30",
     "exports_usd_mn_monthly", 4202.69, 4302.69),
    ("remit", "remit_monthly_mn", "Monthly Remittance", "mn USD", 2858.68, "2026-07-31",
     "remittance_usd_mn_monthly", 2858.68, 2970.0),
    ("dse", "dsex", "DSEX close", "index", 5540.32, "2026-09-20", "dsex", 5540.32, 5501.1),
    ("iran", "iranwar_brent_spot", "Brent spot", "USD/bbl", 67.1, "2026-09-18",
     "brent", 67.1, 69.4),
]
_PAIR_IDS = [f"{p[0]}.{p[1]}" for p in _PAIRS]


def _card_brief(slug: str, label: str, points: list[SeriesPointV6]) -> BriefPayloadV6:
    section = SectionV6(slug=slug, ord=5, title=slug, group_key="markets",
                        metrics=[MetricV6(label=label, value="as built")], series=points)
    return BriefPayloadV6(brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY),
                          sections=[section])


def _raw(slug: str, card_id: str, label: str, unit: str, value: float,
         as_of: str) -> list[dict[str, Any]]:
    return [{"slug": slug, "metrics": [
        {"id": card_id, "label": label, "unit": unit, "value": value, "as_of": as_of}]}]


@pytest.mark.parametrize("pair", _PAIRS, ids=_PAIR_IDS)
def test_card_agreeing_with_its_own_chart_point_raises_no_warning(pair: tuple) -> None:
    slug, cid, label, unit, value, as_of, key, agree, _disagree = pair
    brief = _card_brief(slug, label, [SeriesPointV6(key=key, ts=as_of, value=agree)])
    assert pipeline_v6._check_cards_against_stamped_series(
        brief, _raw(slug, cid, label, unit, value, as_of)) == []


@pytest.mark.parametrize("pair", _PAIRS, ids=_PAIR_IDS)
def test_card_contradicting_its_own_chart_point_is_flagged(pair: tuple) -> None:
    slug, cid, label, unit, value, as_of, key, _agree, disagree = pair
    brief = _card_brief(slug, label, [SeriesPointV6(key=key, ts=as_of, value=disagree)])
    warnings = pipeline_v6._check_cards_against_stamped_series(
        brief, _raw(slug, cid, label, unit, value, as_of))
    assert len(warnings) == 1
    assert f"{slug}.{cid}" in warnings[0] and as_of in warnings[0]
    # Neither number is rewritten: the check only reports.
    assert brief.sections[0].metrics[0].value == "as built"
    assert brief.sections[0].series[0].value == disagree


@pytest.mark.parametrize("pair", _PAIRS, ids=_PAIR_IDS)
def test_no_chart_point_for_the_card_date_is_not_a_contradiction(pair: tuple) -> None:
    """A chart that does not (yet) plot the card's period says nothing about it."""
    slug, cid, label, unit, value, as_of, key, _agree, disagree = pair
    other_day = "2026-01-31"
    brief = _card_brief(slug, label, [SeriesPointV6(key=key, ts=other_day, value=disagree)])
    assert pipeline_v6._check_cards_against_stamped_series(
        brief, _raw(slug, cid, label, unit, value, as_of)) == []


def test_a_card_whose_unit_changed_cannot_be_silently_compared() -> None:
    """The pair's scale rule is only valid for the builder's declared unit."""
    brief = _card_brief("fx", "Monthly Exports",
                        [SeriesPointV6(key="exports_usd_mn_monthly", ts="2026-06-30", value=4202.69)])
    warnings = pipeline_v6._check_cards_against_stamped_series(
        brief, _raw("fx", "fx_monthly_exports", "Monthly Exports", "mn USD", 4202.69, "2026-06-30"))
    assert len(warnings) == 1 and "unit" in warnings[0]


def test_a_card_the_model_did_not_publish_is_not_checked() -> None:
    brief = _card_brief("macro", "Some Other Card",
                        [SeriesPointV6(key="cpi_12m_avg_monthly", ts="2026-07-31", value=8.66)])
    assert pipeline_v6._check_cards_against_stamped_series(
        brief, _raw("macro", "cpi_12m_avg_monthly", "CPI 12m Avg", "%", 8.49, "2026-07-31")) == []


def test_only_the_unambiguous_pairs_are_checked() -> None:
    """Growth of the pair table is a deliberate decision (see the fix-6 report's
    list of ambiguous pairs), not a side effect."""
    expected = {(p[0], p[1], p[6]) for p in _PAIRS}
    actual = {(slug, cid, spec.chart_key)
              for (slug, cid), spec in pipeline_v6._CARD_CHART_PAIRS.items()}
    assert actual == expected


def test_publish_flags_a_card_chart_contradiction_but_rewrites_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End to end: the brief still publishes (WARN policy), the card keeps its
    builder value, the chart keeps its stamped point, and one alert names it."""
    _fake_fetchers(monkeypatch, fetch_macro_cpi_series=lambda *_a, **_k: {
        "cpi_12m_avg_monthly": [SeriesPointV6(key="cpi_12m_avg_monthly", ts="2026-07-31", value=8.66)]})
    card = Metric(id="cpi_12m_avg_monthly", label="CPI 12m Avg", value=8.49, unit="%",
                  as_of=date(2026, 7, 31), source="BBS", cadence="monthly")
    v5 = [SectionData(id="macro", title="Macro", metrics=[card], freshness="fresh")]
    model = [_section_json("macro", 9, "markets",
                           metrics=[{"label": "CPI 12m Avg", "value": "8.49%"}])]
    brief, alerts = _run_publish(monkeypatch, v5_sections=v5, editor_sections=model)

    macro = _by_slug(brief)["macro"]
    assert [m.value for m in macro.metrics] == ["8.49%"]
    assert [p.value for p in macro.series] == [8.66]
    flagged = [a for a in alerts if "card-vs-chart" in a]
    assert len(flagged) == 1 and "macro.cpi_12m_avg_monthly" in flagged[0], alerts


def test_publish_with_agreeing_card_and_chart_sends_no_card_chart_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_fetchers(monkeypatch, fetch_macro_cpi_series=lambda *_a, **_k: {
        "cpi_12m_avg_monthly": [SeriesPointV6(key="cpi_12m_avg_monthly", ts="2026-07-31", value=8.49)]})
    card = Metric(id="cpi_12m_avg_monthly", label="CPI 12m Avg", value=8.49, unit="%",
                  as_of=date(2026, 7, 31), source="BBS", cadence="monthly")
    v5 = [SectionData(id="macro", title="Macro", metrics=[card], freshness="fresh")]
    model = [_section_json("macro", 9, "markets",
                           metrics=[{"label": "CPI 12m Avg", "value": "8.49%"}])]
    _brief, alerts = _run_publish(monkeypatch, v5_sections=v5, editor_sections=model)
    assert [a for a in alerts if "card-vs-chart" in a] == []


# ─── rule 1 (review round 1): per-card sparklines are chart data too ────
# `MetricV6.spark` is drawn by the SPA (StatStack <Sparkline>) and written to
# the /metrics row, but no deterministic code ever stamps it — so any non-empty
# spark on a published card came from the model and is invented by construction.
INVENTED_SPARK = [5100.0, 5200.0, 9999.0]


def _dse_card_sections() -> list[SectionData]:
    card = Metric(id="dsex", label="DSEX close", value=5540.32, unit="index",
                  as_of=date(2026, 9, 20), source="DSE", cadence="daily")
    return [SectionData(id="dse", title="DSE", metrics=[card], freshness="fresh")]


def _dse_model_sections(*, spark: list[float] | None) -> list[dict[str, Any]]:
    metric: dict[str, Any] = {"label": "DSEX close", "value": "5,540.32"}
    if spark is not None:
        metric["spark"] = spark
    return [_section_json("dse", 6, "markets", metrics=[metric])]


@pytest.mark.parametrize("stage", ["editor", "subeditor_revise", "no_credentials"])
def test_model_supplied_card_sparkline_never_reaches_the_published_brief(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, stage: str,
) -> None:
    """An invented sparkline on a card is dropped on every path; the card
    itself (label + builder value) and the stamped chart are kept."""
    _fake_fetchers(monkeypatch)
    invented = _dse_model_sections(spark=INVENTED_SPARK)
    with caplog.at_level(logging.WARNING, logger="brief.pipeline_v6"):
        if stage == "subeditor_revise":
            brief, _ = _run_publish(monkeypatch, v5_sections=_dse_card_sections(),
                                    editor_sections=_dse_model_sections(spark=None),
                                    revised_sections=invented)
        else:
            brief, _ = _run_publish(monkeypatch, v5_sections=_dse_card_sections(),
                                    editor_sections=invented,
                                    credentials=stage != "no_credentials")

    dse = _by_slug(brief)["dse"]
    # R2 fix 7b: the card number is the builder's 5540.32 printed in the house format.
    assert [(m.label, m.value) for m in dse.metrics] == [("DSEX close", "5,540.32")]
    assert [m.spark for m in dse.metrics] == [None], "model sparkline published"
    # What v6_publisher writes to the /metrics row carries no sparkline either.
    assert [m.model_dump(mode="json")["spark"] for m in dse.metrics] == [None]
    if stage != "no_credentials":
        assert dse.series == [STAMPED_DSEX]  # normal stamping unchanged
    discards = [r.getMessage() for r in caplog.records
                if "discarded model-supplied" in r.getMessage()]
    assert any("dse" in m and "spark" in m for m in discards), discards


def test_stamp_helper_itself_clears_a_preexisting_card_sparkline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defence in depth for any caller of `_stamp_chart_series`."""
    _fake_fetchers(monkeypatch)
    brief = BriefPayloadV6(
        brief=BriefV6(issue_no=1, volume=1, brief_date=TODAY),
        sections=[SectionV6.model_validate(s)
                  for s in _dse_model_sections(spark=INVENTED_SPARK)],
    )
    pipeline_v6._stamp_chart_series(
        brief, today=TODAY, http=object(),  # never used: every fetcher is faked
        supabase_url=SUPABASE_URL, service_key=SERVICE_KEY,
    )
    assert [m.spark for m in brief.sections[0].metrics] == [None]
    assert [m.value for m in brief.sections[0].metrics] == ["5,540.32"]
