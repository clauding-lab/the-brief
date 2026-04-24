"""V4 DSE section renderer (§04 EQUITIES).

Extends the generic skeleton with two optional post-grid blocks:

1. Breadth numerals block — advancing / declining / unchanged counts rendered
   as large serif numerals with mono labels.  Injected only when
   ``section.degraded_breadth`` is False.

2. Sector heat 8-tile heatmap — one tile per sector, coloured green (pct >= 0)
   or oxblood (pct < 0) with CSS custom property ``--intensity`` clamped to
   [0, 1] and set to ``abs(pct) / 5``.  Injected only when
   ``section.degraded_sector_heat`` is False AND
   ``section.extras["sector_heat"]`` is a non-empty list.

When ``section.freshness == "unavailable"`` the generic skeleton short-circuits
to a minimal unavailable banner — this module defers to that path entirely.

Sector heat entries may be raw dicts (from the builder JSON) or dataclass-like
objects.  Both shapes are supported:
    dict  → keys "name" or "sector" for the label, "pct" for the value.
    object → attributes .name or .sector, .pct.
"""
from __future__ import annotations

import html as _html

from brief.render.v4.templates._generic import _SECTION_META, render_generic_section
from brief.schema import SectionData

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sector_name(entry: object) -> str:
    """Extract sector label from dict or dataclass-like entry."""
    if isinstance(entry, dict):
        return str(entry.get("name") or entry.get("sector") or "")
    name = getattr(entry, "name", None) or getattr(entry, "sector", None)
    return str(name) if name is not None else ""


def _sector_pct(entry: object) -> float:
    """Extract pct float from dict or dataclass-like entry."""
    if isinstance(entry, dict):
        return float(entry.get("pct", 0.0))
    return float(getattr(entry, "pct", 0.0))


def _breadth_block(section: "SectionData") -> str:
    """Build the breadth numerals HTML block."""
    # Try metrics first (preferred — exact metric IDs)
    metrics_by_id = {m.id: m for m in section.metrics}
    adv = metrics_by_id.get("dse_advancing")
    dec = metrics_by_id.get("dse_declining")
    unch = metrics_by_id.get("dse_unchanged")

    if adv is None and dec is None and unch is None:
        # Fall back to section.extras["breadth"] dict if available
        breadth = section.extras.get("breadth") or {}
        adv_val = breadth.get("advancing", "—")
        dec_val = breadth.get("declining", "—")
        unch_val = breadth.get("unchanged", "—")
    else:
        def _val(m) -> str:
            if m is None:
                return "—"
            v = m.value
            if v is None:
                return "—"
            if isinstance(v, float) and v == int(v):
                return str(int(v))
            return str(v)
        adv_val = _val(adv)
        dec_val = _val(dec)
        unch_val = _val(unch)

    def _item(num: str, label: str) -> str:
        esc_num = _html.escape(str(num), quote=False)
        esc_lbl = _html.escape(label, quote=False)
        return (
            '<div class="breadth-item">'
            f'<span class="num-big">{esc_num}</span>'
            f'<span class="label">{esc_lbl}</span>'
            "</div>"
        )

    return (
        '<div class="dse-breadth">'
        + _item(adv_val, "ADVANCING")
        + _item(dec_val, "DECLINING")
        + _item(unch_val, "UNCHANGED")
        + "</div>"
    )


def _sector_heat_block(entries: list) -> str:
    """Build the sector heat heatmap HTML block."""
    tiles: list[str] = []
    for entry in entries:
        name = _sector_name(entry)
        pct = _sector_pct(entry)
        tile_class = "pos" if pct >= 0 else "neg"
        intensity = min(1.0, abs(pct) / 5.0)
        sign = "+" if pct > 0 else ""
        esc_name = _html.escape(name, quote=False)
        pct_str = f"{sign}{pct:.2f}%"
        tiles.append(
            f'<div class="sector-tile tile-{tile_class}"'
            f' style="--intensity: {intensity:.4f}">'
            f'<span class="sec-name">{esc_name}</span>'
            f'<span class="sec-pct">{pct_str}</span>'
            "</div>"
        )
    return '<div class="dse-sector-heat">' + "".join(tiles) + "</div>"


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------

def render_section_dse(section: "SectionData") -> str:
    """DSE (§04): generic skeleton + breadth numerals + sector heat heatmap."""
    parts: list[str] = []

    if section.freshness != "unavailable":
        # Breadth block
        if not section.degraded_breadth:
            parts.append(_breadth_block(section))

        # Sector heat block
        if not section.degraded_sector_heat:
            heat = section.extras.get("sector_heat") or []
            if heat:
                parts.append(_sector_heat_block(heat))

    post_grid_html = "".join(parts)

    meta = _SECTION_META["dse"]
    return render_generic_section(
        section,
        dom_id="section-dse",
        numeral=meta[0],
        kicker=meta[1],
        title=meta[2],
        bankerread_label=f"§{meta[0]} {meta[2]}",
        post_grid_html=post_grid_html,
    )
