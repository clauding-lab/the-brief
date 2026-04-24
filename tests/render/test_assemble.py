from pathlib import Path
from datetime import date

from brief.render.assemble import replace_function_body, remove_function, Shell


SHELL_PATH = Path(__file__).parent.parent.parent / "fixtures" / "sample_the_brief.html"


def test_replace_function_body_swaps_return():
    src = Path(SHELL_PATH).read_text()
    new_body = 'function SectionBB() {\n  return (<section>NEW_BB</section>);\n}'
    out = replace_function_body(src, "SectionBB", new_body)
    assert "NEW_BB" in out
    assert "OLD_BB_BODY" not in out
    assert "OLD_FX_BODY" in out  # untouched


def test_replace_function_body_noop_on_missing():
    src = Path(SHELL_PATH).read_text()
    out = replace_function_body(src, "DoesNotExist", "function X(){}")
    assert out == src


def test_remove_function_drops_definition_and_usage():
    src = Path(SHELL_PATH).read_text()
    out = remove_function(src, "SectionRMG")
    assert "SectionRMG" not in out
    assert "function SectionBB" in out


def test_shell_roundtrip():
    shell = Shell.load(SHELL_PATH)
    assert "OLD_BB_BODY" in shell.text
    shell.replace("SectionBB", "function SectionBB() { return <x/>; }")
    shell.remove_cut_sections(["SectionRMG"])
    assert "OLD_BB_BODY" not in shell.text
    assert "SectionRMG" not in shell.text


from brief.render.assemble import assemble_brief
from brief.schema import BankerReadStructured, Metric, SectionData


def _section(sid: str, title: str, *, with_br=True) -> SectionData:
    br = BankerReadStructured(
        meaning=f"{sid} one.", action=f"{sid} two.", trigger=f"{sid} three.",
        focus=f"{sid} four.", pull=f"{sid} one.",
    ) if with_br else None
    return SectionData(
        id=sid, title=title, freshness="fresh",
        metrics=[
            Metric(id=f"{sid}_a", label="A", value=1.0, unit="x",
                   as_of=date(2026, 4, 21), source="t", cadence="daily"),
        ],
        bankerread=br,
    )


def test_assemble_brief_replaces_bb_and_fx_removes_rmg():
    sections = [_section("bb", "Policy"), _section("fx", "FX")]
    out = assemble_brief(SHELL_PATH, sections)
    assert "OLD_BB_BODY" not in out
    assert "OLD_FX_BODY" not in out
    assert "OLD_RMG_BODY" not in out
    assert "Policy" in out
    assert "FX" in out
    assert "SectionRMG" not in out


def test_brace_end_handles_jsx_text_apostrophes():
    """Regression: apostrophes in JSX text content (e.g. `Rahman's`) inside a
    `<BankerRead insight="...">` attribute were tripping the brace lexer,
    causing _brace_end to walk hundreds of lines past the real closing brace.
    See `_brace_end` heuristic and limitation note."""
    from brief.render.assemble import _find_function

    shell = (
        "const SectionFoo = React.memo(function SectionFoo() {\n"
        "  return (\n"
        '    <div style={{ display: "flex", alignItems: "center" }}>\n'
        '      <BankerRead insight="Rahman\'s promised gradual rate cut is '
        'unlikely; it\'s a bull\'s gambit." />\n'
        "    </div>\n"
        "  );\n"
        "});\n"
        "\n"
        "function nextFunc() {\n"
        "  return 1;\n"
        "}\n"
    )
    span = _find_function(shell, "SectionFoo")
    assert span is not None
    start, end = span
    body = shell[start:end]
    # The function body MUST end before `nextFunc`; if the lexer walks too
    # far the body would contain `function nextFunc`.
    assert "nextFunc" not in body, (
        "splicer walked past closing brace into next function — "
        "JSX-text apostrophe heuristic regressed"
    )
    assert body.startswith("function SectionFoo()")
    assert body.endswith("}")
