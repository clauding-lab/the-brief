"""V4 Bangladesh Bank section renderer (canonical reference template).

Hero metric strategy: if a metric has hero=True we add class "metric-hero"
directly to the metric-card div (rather than using hero_wrap, which also adds
the class) to keep the card structure flat and predictable.

After Commit 2 this module delegates to render_generic_section so the shared
skeleton logic lives in one place (_generic.py).  All 10 tests in
test_section_bb.py must still pass unchanged after that refactor.
"""
from __future__ import annotations

from brief.render.v4.templates._generic import _SECTION_META, render_generic_section
from brief.schema import SectionData


def render_section_bb(section: "SectionData") -> str:
    """Render Bangladesh Bank section (numeral 02, canonical template)."""
    meta = _SECTION_META["bb"]
    return render_generic_section(
        section,
        dom_id="section-bb",
        numeral=meta[0],
        kicker=meta[1],
        title=meta[2],
        bankerread_label=f"§{meta[0]} {meta[2]}",
    )
