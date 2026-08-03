"""Builder: Macro (CPI + Policy + REER + Credit + External). Monthly cadence.

Per spec §3.6 — this is the macro section's per-section override on the
5-metric cap; the editor prompt explicitly allows 8 metrics here.

Where these 8 numbers come from
-------------------------------
Until v1.6.3 all 8 were read from ``metric_history_monthly``. **That table has
no live writer** — its newest period is 2026-05-01 (ingested 2026-05-05) and
the newest ingest of any kind is a 2023 backfill. So the whole section was
printing numbers 155–183 days old while EconDelta had current readings for
most of them sitting in ``metric_history``, the daily table.

Each metric now declares WHERE its value comes from, and they are no longer all
the same place:

* ``live_id`` — a current series in ``metric_history``. Straight repoint.
* ``derive`` — no single series exists, but the inputs do; computed here.
* ``archive_id`` — nothing live exists ANYWHERE, so it still reads the dead
  archive. These stay old on purpose (see below); they are not an oversight.

**The three archive metrics cannot be fixed by a read-path change.** REER is
absent from every table, ever. CPI 12-month-average is a different measure from
the point-to-point series EconDelta collects, so it cannot be derived from it.
M2 YoY needs 13 months of ``broad_money`` and only 4 exist. Each needs a
scraper, not wiring. They are left reading the archive rather than blanked
because ``section_freshness`` is worst-of, so their real age keeps the whole
section honestly labelled "stale" — the section does NOT start claiming to be
fresh just because five of its eight metrics now are.

AGENTS.md landmine 1 (don't read ``tb_*``) is unaffected — both tables here are
the EconDelta-written ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from brief.cadence import section_freshness
from brief.history import HistoryRow
from brief.history_anchors import HistoryFact, fetch_and_compute
from brief.schema import Metric, SectionData
from . import BuilderContext


@dataclass(frozen=True)
class _Derivation:
    """A macro figure EconDelta does not publish directly, but whose inputs it does.

    `fn` receives the input values in `inputs` order. Both derivations below were
    confirmed against what the old pipeline actually printed before being
    written here, rather than assumed from the metric's name — see each one's
    comment for the arithmetic that reproduces the published figure.
    """

    inputs: tuple[str, ...]
    fn: Callable[..., float]


# Real policy rate = nominal policy rate - point-to-point headline inflation.
# Confirmed: issue #184 printed 1.29%, and 10.00 (the then-current repo rate)
# minus 8.71 (March headline) = 1.29 exactly. `general_inflation` and
# `point_to_point_inflation` carry the same value; the former is the headline id.
_REAL_POLICY_RATE = _Derivation(
    inputs=("policy_rate_repo", "general_inflation"),
    fn=lambda repo, inflation: repo - inflation,
)

# Import cover = gross reserves / one month's imports, both in USD bn.
# Confirmed: issue #184 printed 5.86 months against March reserves of 34.12bn,
# which implies a monthly import bill of 5.82bn — `monthly_import` reads 5.8.
# Cross-check on units: monthly_import x 12 = 69.6 against fy_import_lc 74.78.
_IMPORT_COVER = _Derivation(
    inputs=("gross_reserves_usd_bn", "monthly_import"),
    fn=lambda reserves, monthly_imports: reserves / monthly_imports,
)


@dataclass(frozen=True)
class _MacroSpec:
    """One row of the macro section.

    `id` is the id The Brief PUBLISHES under and never changes — the SPA, the
    metrics table and every downstream consumer key on it. Only the place the
    value is read FROM moves.
    """

    id: str
    label: str
    unit: str
    source: str
    format_kind: str
    live_id: str | None = None
    derive: _Derivation | None = None
    archive_id: str | None = None


_MACRO_METRICS: tuple[_MacroSpec, ...] = (
    # No live source: EconDelta collects point-to-point inflation only, and a
    # 12-month average is a different published measure, not a transform of it.
    _MacroSpec("cpi_12m_avg_monthly", "CPI 12m Avg", "%", "BBS", "percent-1dp",
               archive_id="cpi_12m_avg_monthly"),
    _MacroSpec("cpi_p2p_food_monthly", "CPI Food (P-to-P)", "%", "BBS", "percent-1dp",
               live_id="food_inflation"),
    _MacroSpec("cpi_p2p_nonfood_monthly", "CPI Non-Food (P-to-P)", "%", "BBS", "percent-1dp",
               live_id="non_food_inflation"),
    _MacroSpec("real_policy_rate_monthly", "Real Policy Rate", "%", "BB+BBS", "percent-1dp",
               derive=_REAL_POLICY_RATE),
    # No live source: REER appears in no table, ever. Needs a scraper.
    _MacroSpec("reer_monthly", "REER", "index", "BB", "comma-2dp",
               archive_id="reer_monthly"),
    _MacroSpec("private_credit_growth_yoy_monthly", "Private Credit YoY", "%", "BB",
               "percent-1dp", live_id="private_sector_credit_yoy_pct"),
    # No live source: only the broad_money LEVEL is collected, and only 4 months
    # of it. A year-on-year rate needs 13.
    _MacroSpec("m2_growth_yoy_monthly", "M2 YoY", "%", "BB", "percent-1dp",
               archive_id="m2_growth_yoy_monthly"),
    _MacroSpec("import_cover_months_monthly", "Import Cover", "months", "BB", "comma-1dp",
               derive=_IMPORT_COVER),
)


def _formatter_for(format_kind: str) -> Callable[[float], str]:
    if format_kind == "percent-1dp":
        return lambda v: f"{v:.1f}%"
    if format_kind == "comma-2dp":
        return lambda v: f"{v:,.2f}"
    if format_kind == "comma-1dp":
        return lambda v: f"{v:,.1f}"
    return lambda v: str(v)


def _latest(client, metric_id: str, *, table: str) -> HistoryRow | None:
    """One `get_latest`, tolerating a client that raises.

    A macro metric going dark must not take the section — or the issue — down;
    a missing row already renders as "unavailable".
    """
    try:
        return client.get_latest(metric_id, table=table)
    except Exception:  # noqa: BLE001 — best-effort read, never fatal
        return None


def _derive(client, derivation: _Derivation) -> tuple[float | None, date | None]:
    """Compute a derived figure and date it by its STALEST input.

    Dating it by the freshest input would be the exact failure this section
    exists to stop: issue #184 printed a March REER beside that day's spot rate
    in one clause, because nothing recorded that the two were months apart. A
    derived number is only as current as the oldest thing it is made of.
    """
    values: list[float] = []
    as_ofs: list[date] = []
    for input_id in derivation.inputs:
        row = _latest(client, input_id, table="metric_history")
        if row is None or not isinstance(row.value, (int, float)):
            return (None, None)
        values.append(float(row.value))
        as_ofs.append(row.as_of)
    try:
        return (derivation.fn(*values), min(as_ofs))
    except ZeroDivisionError:
        return (None, None)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    history_facts: list[HistoryFact] = []

    for spec in _MACRO_METRICS:
        value: float | None = None
        as_of: date | None = None

        if spec.derive is not None and ctx.history is not None:
            value, as_of = _derive(ctx.history, spec.derive)
        elif spec.live_id is not None and ctx.history is not None:
            row = _latest(ctx.history, spec.live_id, table="metric_history")
            if row is not None:
                value, as_of = row.value, row.as_of
        elif spec.archive_id is not None and ctx.history_monthly is not None:
            row = _latest(ctx.history_monthly, spec.archive_id,
                          table="metric_history_monthly")
            if row is not None:
                value, as_of = row.value, row.as_of

        metrics.append(Metric(
            id=spec.id,
            label=spec.label,
            value=value,
            unit=spec.unit,
            as_of=as_of if as_of is not None else ctx.today,
            source=spec.source,
            cadence="monthly",  # type: ignore[arg-type]
        ))

        # History facts stay on the archive metrics only, for two reasons.
        # (1) Landmine 23: a builder may not open its own `get_history_window`
        #     against the pipeline's client, and the archive facts run on the
        #     separate `history_monthly` client, as they always have.
        # (2) They would be empty anyway, and worse than empty if they weren't:
        #     the live table holds ~4 months of these series stamped across many
        #     dates (food_inflation = 37 rows, 6 distinct values, 3 months), so
        #     "lowest since" computed over it would be counting restamps as
        #     observations. MIN_DATA_POINTS for monthly is 6 real periods.
        # Revisit once the live series carry a year of genuine monthly points.
        if (
            spec.archive_id is not None
            and ctx.history_monthly is not None
            and value is not None
        ):
            history_facts.extend(fetch_and_compute(
                ctx.history_monthly,
                spec.archive_id,
                cadence="monthly",
                current_value=value,
                formatter=_formatter_for(spec.format_kind),
            ))

    return SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=metrics,
        history_facts=history_facts,
        freshness=section_freshness(metrics, today=ctx.today, section_id="macro"),
    )
