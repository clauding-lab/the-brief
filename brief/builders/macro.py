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

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

from brief.cadence import months_apart, section_freshness
from brief.history import HistoryRow
from brief.history_anchors import HistoryFact, fetch_and_compute
from brief.schema import Metric, SectionData
from . import BuilderContext, official_monthly_bn

logger = logging.getLogger(__name__)

# Each deriver returns (value, as_of, source_override). `source_override` is
# None to keep the spec's default `source` string; a deriver sets it to
# override with metric-specific provenance text (see `_import_cover`'s
# dual-period note, H1 review round 1).
_Deriver = Callable[["BuilderContext"], "tuple[float | None, date | None, str | None]"]


def _at_or_before(client, metric_id: str, as_of: date, *, table: str) -> HistoryRow | None:
    """One `get_at_or_before`, tolerating a client that raises or lacks it.

    Logs a WARNING naming the metric id on any non-success path (M3, review
    round 1) — a dark corridor read must never fail silently.
    """
    try:
        row = client.get_at_or_before(metric_id, as_of, table=table)
    except Exception:  # noqa: BLE001 — best-effort read, never fatal
        logger.warning(
            "macro: get_at_or_before(%s, %s) raised, treating as absent",
            metric_id, as_of, exc_info=True,
        )
        return None
    if row is None:
        logger.warning("macro: get_at_or_before(%s, %s) — no row found", metric_id, as_of)
    return row


def _real_policy_rate(ctx: "BuilderContext") -> tuple[float | None, date | None, str | None]:
    """Real policy rate = the repo rate IN FORCE on the inflation reading's
    date, minus that same reading (period-consistent; P0 honesty fix, 2026-08-22
    audit #204).

    Pairing "latest repo" with "latest inflation" mixes vintages whenever a cut
    lands between the two prints. On 2026-08-22 the live repo read 9.50 (post
    the 30-Jul cut) while the latest inflation print was still June's, so the
    old arithmetic (9.50 - 9.16 = 0.34%) described a rate that never actually
    existed alongside that inflation reading. The June-consistent value is the
    repo rate AS OF 30 Jun (10.00, pre-cut) minus June's inflation (9.16) =
    0.84%. `as_of` is the inflation date — that is the period this figure
    describes.
    """
    if ctx.history is None:
        return (None, None, None)
    inflation = _latest(ctx.history, "general_inflation", table="metric_history")
    if inflation is None or not isinstance(inflation.value, (int, float)):
        logger.warning("macro: real_policy_rate suppressed — general_inflation unavailable")
        return (None, None, None)
    repo = _at_or_before(ctx.history, "policy_rate_repo", inflation.as_of, table="metric_history")
    if repo is None or not isinstance(repo.value, (int, float)):
        logger.warning(
            "macro: real_policy_rate suppressed — no policy_rate_repo at or before %s",
            inflation.as_of,
        )
        return (None, None, None)
    return (repo.value - inflation.value, inflation.as_of, None)


# ORCHESTRATOR DECISION (2026-08-22 audit #204, review round 1, H1): import
# cover is a stock (reserves) over a flow (the most recent official import
# bill), and BB's own methodology tolerates the flow leg running several
# months behind the stock leg — that is just how customs-cleared import data
# is reported. Production today (Jul reserves vs Mar imports) is 4 months
# apart. The trade gap in fx.py stays same-month-only: that IS a flow-vs-flow
# comparison, where mixing vintages is genuinely meaningless.
_IMPORT_COVER_MAX_MONTHS_APART = 4


def _import_cover(ctx: "BuilderContext") -> tuple[float | None, date | None, str | None]:
    """Import cover = gross reserves / the latest OFFICIAL monthly imports.

    ORCHESTRATOR DECISION (2026-08-22 audit #204, review round 1, H1) —
    replaces the first cut's >1-month suppression rule. That rule suppressed
    the metric (value=None) on every real production day, because BB's
    customs-cleared import figure runs months behind reserves by nature — and
    a suppressed metric scores "unavailable" in `section_freshness`, which
    macro (in `SECTIONS_WITHOUT_LEGACY_BACKFILL`) PROMOTES to "warming_up".
    That flipped §03's honestly "stale" badge (driven by the three still-
    archived metrics: REER, CPI 12m avg, M2 YoY) into a false "history is
    accumulating" signal — worse than the mismatch it was trying to prevent.

    The fix re-emits the ratio whenever the official imports archive is
    within `_IMPORT_COVER_MAX_MONTHS_APART` months of the reserves reading.
    `as_of` is dated by the IMPORTS month specifically (the rate-limiting,
    always-older leg) — never the fresher reserves date, and never min() of
    the two — so the metric's OWN freshness stays honest: stale imports keep
    §03 reading "stale", which is the entire point of this fix. `source`
    (returned as this function's third element, an override of the spec's
    default "BB") names BOTH periods explicitly, e.g.
    "BB (reserves 31 Jul ÷ Mar import bill)", so the two-vintage nature of
    the ratio is never silently implied to be a single, current read.

    Suppressed (returns all-None) only when either leg is missing or imports
    are more than `_IMPORT_COVER_MAX_MONTHS_APART` months older than reserves.
    """
    if ctx.history is None:
        return (None, None, None)
    reserves = _latest(ctx.history, "gross_reserves_usd_bn", table="metric_history")
    if reserves is None or not isinstance(reserves.value, (int, float)):
        logger.warning("macro: import_cover suppressed — gross_reserves_usd_bn unavailable")
        return (None, None, None)
    imports = official_monthly_bn(ctx, "imports_usd_mn_monthly")
    if imports is None:
        logger.warning("macro: import_cover suppressed — imports_usd_mn_monthly unavailable")
        return (None, None, None)
    gap = months_apart(reserves.as_of, imports.as_of)
    if gap > _IMPORT_COVER_MAX_MONTHS_APART:
        logger.warning(
            "macro: import_cover suppressed — imports_usd_mn_monthly is %d months "
            "behind reserves (max %d)", gap, _IMPORT_COVER_MAX_MONTHS_APART,
        )
        return (None, None, None)
    try:
        cover = reserves.value / imports.value
    except ZeroDivisionError:
        return (None, None, None)
    note = f"BB (reserves {reserves.as_of:%-d %b} ÷ {imports.as_of:%b} import bill)"
    return (cover, imports.as_of, note)


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
    derive: _Deriver | None = None
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
               derive=_real_policy_rate),
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
               derive=_import_cover),
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


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    history_facts: list[HistoryFact] = []

    for spec in _MACRO_METRICS:
        value: float | None = None
        as_of: date | None = None
        source: str = spec.source

        if spec.derive is not None:
            value, as_of, source_override = spec.derive(ctx)
            if source_override is not None:
                source = source_override
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
            source=source,
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
