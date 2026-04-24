from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionFX", dom_id="section-fx")
