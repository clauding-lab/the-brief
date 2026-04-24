"""V4 Domestic Food Prices section renderer — thin binder over render_generic_section."""
from __future__ import annotations

from brief.render.v4.templates._generic import _SECTION_META, render_generic_section
from brief.schema import SectionData


def render_section_dam(section: "SectionData") -> str:
    """Render Domestic Food Prices section (numeral 08)."""
    meta = _SECTION_META["dam"]
    return render_generic_section(
        section,
        dom_id="section-dam",
        numeral=meta[0],
        kicker=meta[1],
        title=meta[2],
        bankerread_label=f"§{meta[0]} {meta[2]}",
    )
