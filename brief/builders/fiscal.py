"""Builder: Fiscal — monthly NBR collections and government bank borrowing.

`fiscal_nbr_target_trn` ("NBR full-year target") and `fiscal_adp_pct` ("ADP
utilisation") were removed in v1.6.6. Neither id has ever had a single row in
`metric_history` or `metric_history_monthly` — not stale, never written, by any
scraper in either repo. They rendered as permanently blank tiles.

That was not merely cosmetic. `value is None` scores "unavailable", and because
`fiscal` is in `SECTIONS_WITHOUT_LEGACY_BACKFILL` that gets promoted to
"warming_up" — so the section wore a badge promising data was on its way, for
data that had nothing behind it. With them gone the section reads "fresh", which
is what its two live metrics actually are.

The target is the real loss: "NBR collected YTD 3.61 trn" wants "against an
X trn target" next to it, and that is the half a desk acts on. It is a published
budget figure, so the fix is to source it — not to hardcode a constant here.
Hardcoding is exactly how the policy corridor came to print a superseded 10.0%
for weeks (landmine 24, and `bb.py`'s fallbacks). Re-add it wired to history the
day a scraper writes it.
"""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


_SPEC = (
    ("fiscal_nbr_collected_trn", "NBR collected YTD", "BDT trn", "NBR"),
    ("fiscal_govt_borrow_trn",   "Govt bank borrow YTD", "BDT trn", "BB"),
)


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    for mid, label, unit, source in _SPEC:
        last = ctx.history.get_latest(mid) if ctx.history is not None else None
        metrics.append(Metric(
            id=mid, label=label,
            value=(last.value if last else None), unit=unit,
            as_of=(last.as_of if last else ctx.today),
            source=source, cadence="monthly",
        ))
    return SectionData(
        id="fiscal", title="Fiscal", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today, section_id="fiscal"),
    )
