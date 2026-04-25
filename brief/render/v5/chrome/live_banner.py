"""V5 live status banner — top of page, oxblood, mono."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from brief.render.v5._jsx import _esc, fmt_num


def render_live_banner(live: dict[str, Any]) -> str:
    """Top-of-page status strip with live market values.

    Pure data — no Claude. Inputs come from EconDelta + Supabase via the
    pipeline gather stage.

    Schema: live = {
        usd_bdt: float | None,
        dsex: int | float | None,
        brent_usd: float | None,
        reserves_bn_usd: float | None,
        generated_at: datetime,
        next_update_label: str,
    }
    """
    def _val(x, fmt: str = "{:.2f}") -> str:
        return fmt.format(x) if x is not None else "—"

    time_label = live["generated_at"].strftime("%H:%M")
    usd = _val(live.get("usd_bdt"))
    dsex = _val(live.get("dsex"), "{:,.0f}")
    brent = _val(live.get("brent_usd"))
    reserves = _val(live.get("reserves_bn_usd"))
    nxt = _esc(live.get("next_update_label", ""))

    return (
        '<section class="live-banner" aria-label="Live market status">'
        '<div class="live-banner-inner">'
        f'<span class="lb-stamp"><span class="lb-dot">●</span> LIVE · {_esc(time_label)} BDT · DHAKA</span>'
        '<span class="lb-grid">'
        f'<span class="lb-field"><span class="lb-key">USD/BDT</span> <span class="lb-val">{_esc(usd)}</span></span>'
        f'<span class="lb-field"><span class="lb-key">DSEX</span> <span class="lb-val">{_esc(dsex)}</span></span>'
        f'<span class="lb-field"><span class="lb-key">BRENT</span> <span class="lb-val">${_esc(brent)}</span></span>'
        f'<span class="lb-field"><span class="lb-key">RESERVES</span> <span class="lb-val">${_esc(reserves)}BN</span></span>'
        '</span>'
        f'<span class="lb-next">NEXT UPDATE · {nxt}</span>'
        '</div>'
        '</section>'
    )
