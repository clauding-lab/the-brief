from brief.render.templates.section_exec import render
from brief.schema import ExecSignal, SectionData


def _section():
    return SectionData(
        id="exec", title="Executive Signals", freshness="fresh",
        exec_signals=[
            ExecSignal(direction="bull", text="Reserves up 0.3bn WoW",
                       section_anchor="bb"),
            ExecSignal(direction="warn", text="Oil +5% on Iran risk",
                       section_anchor="iranwar"),
        ],
    )


def test_exec_render_shows_signals():
    out = render(_section())
    assert out.startswith("function SectionExec()")
    assert "Reserves up" in out
    assert "Oil +5%" in out
    assert 'direction: "bull"' in out
