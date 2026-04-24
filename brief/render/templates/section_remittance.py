from brief.render.templates._metric_card_section import render_generic
from brief.schema import SectionData


def render(section: SectionData) -> str:
    return render_generic(section, component_name="SectionRemittance", dom_id="section-remit")
