"""Builder: Commodities — gold (from EconDelta), LNG (from history).

LNG reads `lng_price_usd_mmbtu`, NOT `comm_lng_jkm`. Both exist in
`metric_history`; only one of them is still written.

`comm_lng_jkm` was the JKM spot marker, last written 2026-04-20 and dead ever
since — no scraper in either repo produces it, and its 12 rows came from a
hand-run "manual"/"claude-daily" ingest that stopped. It sat on the page at
15.00 USD/MMBtu for 105 days looking like a price.

`lng_price_usd_mmbtu` comes from EconDelta's World Bank Pink Sheet scraper
(`scrapers/world_bank_pink_sheet.py`) and is live. It is a DIFFERENT series —
the Pink Sheet's "Liquefied natural gas, Japan", i.e. Japan's monthly average
IMPORT price, contract-weighted — not a spot cargo marker. Hence the label says
"LNG (Japan)" and the source names the Pink Sheet: swapping the value while
keeping the old label would print one market's price under another's name, and
this brief's readers price LNG for a living.

Cadence is monthly because the Pink Sheet is monthly and its as_of is stamped to
the reporting month's last day. Note that the Pink Sheet scraper's download URL
is edition-pinned upstream and has silently frozen before (their landmine, not
ours) — `brief.vintage` is what makes that visible here rather than invisible.
"""
from __future__ import annotations

from brief.cadence import section_freshness
from brief.schema import Metric, SectionData
from . import BuilderContext


def build(ctx: BuilderContext) -> SectionData:
    gold_oz = ctx.snapshot.get("gold_usd_oz")

    last_lng = (
        ctx.history.get_latest("lng_price_usd_mmbtu") if ctx.history is not None else None
    )

    metrics = [
        Metric(id="comm_gold_usd_oz", label="Gold", value=gold_oz,
               unit="USD/oz", as_of=ctx.today, source="EconDelta", cadence="daily"),
        Metric(id="lng_price_usd_mmbtu", label="LNG (Japan)",
               value=(last_lng.value if last_lng else None),
               unit="USD/MMBtu",
               as_of=(last_lng.as_of if last_lng else ctx.today),
               source="World Bank Pink Sheet", cadence="monthly"),
    ]
    return SectionData(
        id="comm", title="Commodities", metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )
