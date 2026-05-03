"""V4 FX & Reserves section renderer — thin binder over render_generic_section."""
from __future__ import annotations

from brief.render.v4.templates._generic import _SECTION_META, render_generic_section
from brief.schema import SectionData


def render_section_fx(section: "SectionData") -> str:
    """Render FX & Reserves section (numeral 06)."""
    meta = _SECTION_META["fx"]
    return render_generic_section(
        section,
        dom_id="section-fx",
        numeral=meta[0],
        kicker=meta[1],
        title=meta[2],
        bankerread_label=f"§{meta[0]} {meta[2]}",
    )
