"""Builder: DSE daily market snapshot."""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.history import HistoryRow
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("dse_dsex_close",       "DSEX close",       "dsex",              "index"),
    ("dse_dsex_change_pct",  "DSEX %Δ",          "dsex_change_pct",   "%"),
    ("dse_ds30",             "DS30",             "ds30",              "index"),
    ("dse_dses",             "DSES",             "dses",              "index"),
    ("dse_turnover_crore",   "Turnover",         "turnover_crore",    "crore BDT"),
    ("dse_advancing",        "Advancing",        "advancing",         "stocks"),
    ("dse_declining",        "Declining",        "declining",         "stocks"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics = [
        Metric(
            id=mid,
            label=label,
            value=ctx.snapshot.get(src_key),
            unit=unit,
            as_of=ctx.today,
            source="DSE (via EconDelta)",
            source_url="https://www.dse.com.bd/market-statistics.php",
            cadence="daily",
        )
        for (mid, label, src_key, unit) in _SPEC
    ]

    # Upsert DSEX close for history + downstream chart delta
    dsex = ctx.snapshot.get("dsex")
    if ctx.history is not None and dsex is not None:
        ctx.history.upsert_many([
            HistoryRow("dse_dsex_close", ctx.today, float(dsex), "DSE"),
        ])

    return SectionData(
        id="dse",
        title="DSE Markets",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
