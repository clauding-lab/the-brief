import pytest

from brief.render.v5.templates.section_exec import render_section_exec
from brief.schema import ExecSignal, SectionData


def _exec_section(*, signals: list[ExecSignal] | None = None) -> SectionData:
    if signals is None:
        signals = [
            ExecSignal(direction="bull", text="Reserves rebuild remains intact through Q1.",
                       section_anchor="bb"),
            ExecSignal(direction="bear", text="Headline CPI base effects fade in May.",
                       section_anchor="macro"),
            ExecSignal(direction="warn", text="USD/BDT mid drifts above 124 trigger.",
                       section_anchor="fx"),
            ExecSignal(direction="watch", text="OPEC+ output decision next week.",
                       section_anchor="iranwar"),
        ]
    return SectionData(
        id="exec", title="Executive Signals",
        kicker="EXEC SIGNALS", tldr=f"{len(signals)} signals",
        metrics=[], news=[], freshness="fresh" if signals else "pending",
        exec_signals=signals or None,
    )


def test_section_exec_renders_with_full_data():
    html = render_section_exec(_exec_section())
    assert 'id="section-exec"' in html
    assert "§14" in html
    assert "EXEC SIGNALS" in html
    # All four direction classes present
    assert "exec-signal-bull" in html
    assert "exec-signal-bear" in html
    assert "exec-signal-warn" in html
    assert "exec-signal-watch" in html
    # Direction arrows
    assert "▲" in html  # bull
    assert "▼" in html  # bear
    # Signal text
    assert "Reserves rebuild" in html
    # Anchor links resolve to §NN
    assert "→ §02" in html  # bb section
    assert "→ §03" in html  # macro section
    assert "→ §04" in html  # fx section
    assert "→ §08" in html  # iranwar section
    # No metric cards, no sparkline
    assert "metric-card" not in html
    assert "sparkline" not in html


def test_section_exec_renders_with_no_signals():
    html = render_section_exec(_exec_section(signals=[]))
    assert 'id="section-exec"' in html
    assert "exec-signals" not in html
    assert "exec-signal-" not in html


def test_section_exec_renders_with_one_signal():
    one = [ExecSignal(direction="bull", text="Solo signal.", section_anchor="bb")]
    html = render_section_exec(_exec_section(signals=one))
    assert "exec-signal-bull" in html
    assert "Solo signal." in html
    assert "→ §02" in html
    # Only one li
    assert html.count('<li class="exec-signal ') == 1


def test_section_exec_no_threshold_badge_in_render():
    """Exec has no metrics; badge must never appear."""
    html = render_section_exec(_exec_section())
    assert "CRITICAL" not in html
    assert "WATCH" not in html


def test_section_exec_rejects_wrong_id():
    section = _exec_section().model_copy(update={"id": "fx"})
    with pytest.raises(ValueError):
        render_section_exec(section)
