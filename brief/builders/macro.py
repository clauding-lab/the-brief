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


# Review round 2026-08-27: the guard branch resolves the repo leg from the
# LATEST restamp, which is unbounded in time — same failure shape the import
# cover gate below already guards against, so it takes the same 4-month
# bound. Past it the pair is not period-consistent and the metric is
# suppressed (landmine 27(b)) rather than printed with an invented vintage.
_REAL_POLICY_MAX_MONTHS_APART = 4


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

    Inflation leg = `point_to_point_inflation` (current-month y/y CPI), the
    market convention for a real policy rate. Paired with econdelta PR #126
    (2026-08-23), which anchors `general_inflation` to BB's twelve-month
    AVERAGE column — a trailing measure that would understate the real rate
    by construction. Before #126 the two ids carried the same p2p number, so
    this repoint changes nothing retroactively; after it, each id has one
    well-defined meaning. Owner veto invited (landmine 49(a) pairing).

    THE RESTAMP-LAG GUARD (2026-08-26)
    ----------------------------------
    "The repo rate at_or_before the inflation date" is only the rate in force
    if EconDelta had already restamped the corridor by then. It hadn't. The
    30 Jul MPC cut (10.00 -> 9.50) did not reach `policy_rate_repo` until
    03 Aug, so every restamped row from 25 Jul through 02 Aug still carried
    10.00 — including the 31 Jul row this function reads for July's CPI
    print. Landmine 24 in one line: `as_of` on a `policy_rate_*` row is the
    day EconDelta re-upserted it, never the day the corridor moved.

    Production shipped the consequence on 2026-08-26: 10.00 - 8.32 = 1.68%,
    presented as the real rate "after the July cut" while being computed
    entirely from the PRE-cut rate. The honest figure is 9.50 - 8.32 = 1.18%,
    a 50bp overstatement of how restrictive policy actually is.

    So: when the latest MPC decision landed ON or BEFORE the inflation
    reading's own date (`bb._LAST_MPC_DECISION <= inflation.as_of`), the
    corridor had already moved by the time that CPI print was taken, and the
    `at_or_before` row is suspect — resolve the repo leg from the LATEST row
    instead. That row is safe *precisely because* `_LAST_MPC_DECISION` is the
    most recent decision: if it is not after the inflation date, then no
    decision is, so today's standing corridor IS the rate that was in force.
    When the decision is LATER than the inflation date (June's print vs the
    30 Jul cut) the guard stays out of the way and `at_or_before` remains
    correct — that case still reads 10.00 - 9.16 = 0.84%.

    `_LAST_MPC_DECISION` is imported rather than re-declared so there is one
    decision date in the codebase; `tests/builders/test_bb.py::
    test_fallback_constants_match_the_latest_mpc_decision` pins it, and
    landmine 24 already requires bumping it in the PR that reacts to a move.
    The guard reads with `get_latest`, never `get_history_window` — landmine
    23 forbids a builder opening a second window fetch.

    Either leg missing returns all-None: half a derivation is not a number
    (landmine 27(b)). The third element is a provenance note naming BOTH legs
    and the inflation month; `pipeline_v6._stamp_real_policy_rate_sub` is what
    carries it to the reader, since `MetricV6` has no `source` field.

    THE GUARD'S OWN BOUNDS (review round, 2026-08-27)
    -------------------------------------------------
    (1) STALENESS. `get_latest` returns the freshest restamp however far it
    has drifted from the CPI print. A corridor that keeps restamping while
    the inflation feed dies would otherwise pair, say, a 2027 rate with a
    2026 reading and date the difference by the 2026 reading. The guard
    branch is bounded by `_REAL_POLICY_MAX_MONTHS_APART`, the same 4-month
    shape (and same rationale) as `_IMPORT_COVER_MAX_MONTHS_APART`; past it
    the metric is suppressed rather than invented.

    (2) SINGLE DECISION DATE — a known, documented limit, not an oversight.
    `_LAST_MPC_DECISION` records only the MOST RECENT move, so once a NEWER
    decision lands while the CPI feed is still stalled on an older print, the
    comparison goes False again and the at_or_before branch resumes — which
    can re-print the very restamp-lag value this fix removes. Pinned by
    `test_real_policy_rate_after_a_newer_decision_reverts_to_the_at_or_before_branch`
    so it can only ever change deliberately. Closing it properly needs a real
    corridor EFFECTIVE-DATE series from EconDelta (each rate carrying the day
    it began to apply), not more inference here.
    """
    # Local import: `bb` and `macro` are sibling builders with no import
    # relationship otherwise, and this keeps the decision date single-sourced.
    from brief.builders.bb import _LAST_MPC_DECISION

    if ctx.history is None:
        return (None, None, None)
    inflation = _latest(ctx.history, "point_to_point_inflation", table="metric_history")
    if inflation is None or not isinstance(inflation.value, (int, float)):
        logger.warning("macro: real_policy_rate suppressed — point_to_point_inflation unavailable")
        return (None, None, None)

    if _LAST_MPC_DECISION <= inflation.as_of:
        # Corridor moved on or before this CPI print — the at_or_before row
        # may still be a pre-decision restamp. Take the standing corridor.
        repo = _latest(ctx.history, "policy_rate_repo", table="metric_history")
        if repo is None or not isinstance(repo.value, (int, float)):
            logger.warning(
                "macro: real_policy_rate suppressed — no latest policy_rate_repo to "
                "resolve the rate in force on %s (MPC decision %s)",
                inflation.as_of, _LAST_MPC_DECISION,
            )
            return (None, None, None)
        gap = months_apart(repo.as_of, inflation.as_of)
        if gap > _REAL_POLICY_MAX_MONTHS_APART:
            logger.warning(
                "macro: real_policy_rate suppressed — the latest policy_rate_repo "
                "restamp (%s) is %d months from the %s inflation print (max %d); "
                "pairing them would date a much later rate by a much older reading",
                repo.as_of, gap, inflation.as_of, _REAL_POLICY_MAX_MONTHS_APART,
            )
            return (None, None, None)
        logger.info(
            "macro: real_policy_rate repo leg taken from the LATEST restamp (%.2f) — "
            "the %s MPC decision predates the %s inflation print, so the at_or_before "
            "row can still carry the pre-decision rate",
            repo.value, _LAST_MPC_DECISION, inflation.as_of,
        )
        # The repo leg is dated by the DECISION, never by `repo.as_of` — that
        # is a restamp date, and landmine 24 forbids presenting it as the day
        # the rate changed. This is the branch where the two differ.
        repo_leg = f"{repo.value:.2f}% repo ({_LAST_MPC_DECISION:%-d %b} cut)"
    else:
        repo = _at_or_before(
            ctx.history, "policy_rate_repo", inflation.as_of, table="metric_history"
        )
        if repo is None or not isinstance(repo.value, (int, float)):
            logger.warning(
                "macro: real_policy_rate suppressed — no policy_rate_repo at or before %s",
                inflation.as_of,
            )
            return (None, None, None)
        # No decision sits between the two vintages, so there is no cut to
        # name and nothing the undated form could mislead about.
        repo_leg = f"{repo.value:.2f}% repo"

    # "repo" + "p2p CPI" is the marker pair `pipeline_v6._stamp_real_policy_
    # rate_sub` and `validators.prose_numbers._is_machine_stamped_real_policy_
    # rate` both key on — change the wording here and both must move with it.
    # Minus is Master.md's GLYPH (−, U+2212), never the ASCII hyphen.
    note = (
        f"BB+BBS ({repo_leg} − {inflation.value:.2f}% "
        f"{inflation.as_of:%b} p2p CPI)"
    )
    return (repo.value - inflation.value, inflation.as_of, note)


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
    §03 reading "stale", which is the entire point of this fix.

    `source` (returned as this function's third element, an override of the
    spec's default "BB") carries the dual-period note, e.g.
    "BB (reserves 31 Jul ÷ Mar import bill)". SOFTENED CLAIM (M-A, review
    round 2): this function does NOT by itself guarantee a reader ever sees
    that note — `MetricV6`, the schema the editor's output is validated
    against, has no `source` field, so it is dropped at validation time no
    matter what the editor does with it. The note only reaches the reader
    because `pipeline_v6._stamp_import_cover_sub` reads THIS `source` string
    back out of the raw builder output and deterministically writes it into
    the published metric's `sub` field after the editor runs. This function's
    only real guarantee is that the dual-period fact is computed and recorded
    somewhere in the raw payload — a downstream pass is what makes it visible.

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
    # Issue 206, item 4 — per-spec OPT-IN only (today: the CPI food/non-food
    # pair). When True, both `live_id` (daily) and `archive_id` (monthly) are
    # read and the NEWEST row that counts as OFFICIAL wins — see
    # `_resolve_newest_official_cpi`. Every other live_id spec (private
    # credit, etc.) is UNCHANGED: it stays on its single `metric_history`
    # read, exactly as before this fix (review round-2 risk note — a blanket
    # elif→resolver change would silently repoint specs nobody audited).
    dual_source_official: bool = False


_MACRO_METRICS: tuple[_MacroSpec, ...] = (
    # No live source: EconDelta collects point-to-point inflation only, and a
    # 12-month average is a different published measure, not a transform of it.
    _MacroSpec("cpi_12m_avg_monthly", "CPI 12m Avg", "%", "BBS", "percent-1dp",
               archive_id="cpi_12m_avg_monthly"),
    # Issue 206, item 4: both a live daily read AND the monthly archive —
    # `dual_source_official=True` scopes the new resolver to just this pair.
    # With today's real data (archive July unofficial for both legs of this
    # pair) these still resolve to June's daily print; the card values do
    # NOT change from before this fix.
    _MacroSpec("cpi_p2p_food_monthly", "CPI Food (P-to-P)", "%", "BBS", "percent-1dp",
               live_id="food_inflation", archive_id="cpi_p2p_food_monthly",
               dual_source_official=True),
    _MacroSpec("cpi_p2p_nonfood_monthly", "CPI Non-Food (P-to-P)", "%", "BBS", "percent-1dp",
               live_id="non_food_inflation", archive_id="cpi_p2p_nonfood_monthly",
               dual_source_official=True),
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
    a missing row already renders as "unavailable". Feeds 5 of the section's
    8 published metrics (the 3 direct `live_id` reads, plus `point_to_point_inflation`
    inside `_real_policy_rate` — which since 2026-08-26 also reads
    `policy_rate_repo` through here on its restamp-lag branch — and
    `gross_reserves_usd_bn` inside
    `_import_cover`), so a silent swallow here was a wide blind spot — logs a
    WARNING naming the metric id on both non-success paths (M-C, review
    round 2, matching the M3 treatment already given to `official_monthly_bn`
    and `_at_or_before`).
    """
    try:
        row = client.get_latest(metric_id, table=table)
    except Exception:  # noqa: BLE001 — best-effort read, never fatal
        logger.warning(
            "macro: get_latest(%s, table=%s) raised, treating as absent",
            metric_id, table, exc_info=True,
        )
        return None
    if row is None:
        logger.warning("macro: get_latest(%s, table=%s) — no row found", metric_id, table)
    return row


def _resolve_newest_official_cpi(
    ctx: "BuilderContext", spec: "_MacroSpec",
) -> tuple[float | None, date | None]:
    """Newest OFFICIAL row across BOTH `metric_history` (`spec.live_id`,
    daily) and `metric_history_monthly` (`spec.archive_id`, monthly) for ONE
    CPI concept (issue 206, item 4). SCOPED to specs that opt in via
    `dual_source_official=True` — today, only the CPI food/non-food pair.

    The live daily leg is trusted as-is (EconDelta's own scrape, unfiltered
    — the same contract every other `live_id` spec already has). The
    monthly archive leg is filtered through `chart_series_fetcher`'s CPI
    honesty gate (`is_official_cpi_point`) — the SAME predicate the chart
    uses, so a card and its own chart can never independently disagree on
    what counts as official for this pair.

    With production's real 2026-08-24 shape (June daily official, July
    archive unofficial for both legs of this pair) this resolves to the
    JUNE daily row for both cards — the card values do not move to July.
    """
    from brief.chart_series_fetcher import is_official_cpi_point

    candidates: list[HistoryRow] = []
    if spec.live_id is not None and ctx.history is not None:
        row = _latest(ctx.history, spec.live_id, table="metric_history")
        if row is not None and isinstance(row.value, (int, float)):
            candidates.append(row)
    if spec.archive_id is not None and ctx.history_monthly is not None:
        row = _latest(ctx.history_monthly, spec.archive_id, table="metric_history_monthly")
        if (
            row is not None
            and isinstance(row.value, (int, float))
            and is_official_cpi_point(spec.archive_id, row.as_of.isoformat(), row.source)
        ):
            candidates.append(row)
    if not candidates:
        return (None, None)
    newest = max(candidates, key=lambda r: r.as_of)
    return (newest.value, newest.as_of)


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
        elif spec.dual_source_official:
            value, as_of = _resolve_newest_official_cpi(ctx, spec)
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
        #
        # Issue 206, item 4: `dual_source_official` specs (CPI food/non-food)
        # now ALSO carry `archive_id`, but must NOT gain history facts here —
        # that would be new behaviour beyond this fix's scope, and it would
        # compute "lowest since" claims against an archive series that can
        # include unofficial/derived points `is_official_cpi_point` filters
        # out of the CHART but this block does not filter at all. Excluded
        # explicitly so these two specs stay exactly as before this fix.
        if (
            spec.archive_id is not None
            and not spec.dual_source_official
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
