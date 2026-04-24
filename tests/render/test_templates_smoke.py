import importlib

import pytest

from brief.schema import SectionData


_CASES = [
    ("brief.render.templates.section_macro",      "SectionMacro",      "macro"),
    ("brief.render.templates.section_fx",         "SectionFX",         "fx"),
    ("brief.render.templates.section_remittance", "SectionRemittance", "remit"),
    ("brief.render.templates.section_tbond",      "SectionTBond",      "tbond"),
    ("brief.render.templates.section_iranwar",    "SectionIranWar",    "iranwar"),
    ("brief.render.templates.section_comm",       "SectionComm",       "comm"),
    ("brief.render.templates.section_banking",    "SectionBanking",    "banking"),
    ("brief.render.templates.section_dam",        "SectionDAM",        "dam"),
    ("brief.render.templates.section_fiscal",     "SectionFiscal",     "fiscal"),
    ("brief.render.templates.section_nbr",        "SectionNBR",        "nbr"),
]


@pytest.mark.parametrize("modname,component,sid", _CASES)
def test_template_renders_empty_section(modname, component, sid):
    mod = importlib.import_module(modname)
    s = SectionData(id=sid, title=f"{component} title", freshness="fresh")
    out = mod.render(s)
    assert out.startswith(f"function {component}()")
    assert f'id="section-{sid}"' in out
