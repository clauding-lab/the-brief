from pathlib import Path

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
