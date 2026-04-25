"""Tests for brief.render.v4.assemble — V4 shell splicer."""
from __future__ import annotations

from pathlib import Path

import pytest

from brief.render.v4.assemble import AssembleError, assemble_brief, load_shell, splice

# Path to the miniature fixture
FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "fixtures" / "sample_shell_v4.html"

# All 18 SPLICE placeholder names (must match shell_v4.html and assemble.py)
ALL_PLACEHOLDERS = [
    "dateline",
    "masthead_todays_call",
    "risk_map",
    "flow_index",
    "section_headlines",
    "section_bb",
    "section_banking",
    "section_dse",
    "section_tbond",
    "section_fx",
    "section_macro",
    "section_dam",
    "section_comm",
    "section_remit",
    "section_iranwar",
    "section_fiscal",
    "section_nbr",
    "colophon",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_run_result():
    """Build a minimal RunResult for assembler tests — no real Claude data."""
    from datetime import datetime, timezone
    from brief.pipeline import RunResult
    from brief.schema import SectionData, TodaysCall

    sections = [
        SectionData(id=sid, title=sid.upper(), freshness="fresh")
        for sid in [
            "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
            "headlines", "exec", "comm", "banking", "dam", "fiscal", "nbr",
        ]
    ]
    return RunResult(
        sections=sections,
        html="",
        claude_outputs={},
        call_reports=[],
        map_coords=[],
        todays_call=TodaysCall(text="Test call.", generated_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
        read_order=["bb"],
    )


# ---------------------------------------------------------------------------
# splice() tests
# ---------------------------------------------------------------------------

class TestSplice:
    def test_valid_placeholder_is_replaced(self) -> None:
        shell = "<div><!-- SPLICE:dateline --></div>"
        result = splice(shell, "dateline", "<p>DATE</p>")
        assert "<p>DATE</p>" in result
        assert "<!-- SPLICE:dateline -->" not in result

    def test_missing_placeholder_raises_assemble_error(self) -> None:
        shell = "<div><!-- SPLICE:other --></div>"
        with pytest.raises(AssembleError, match="not found or ambiguous"):
            splice(shell, "dateline", "<p>DATE</p>")

    def test_duplicate_placeholder_raises_assemble_error(self) -> None:
        shell = "<!-- SPLICE:dateline --><!-- SPLICE:dateline -->"
        with pytest.raises(AssembleError, match="not found or ambiguous"):
            splice(shell, "dateline", "<p>DATE</p>")

    def test_replacement_content_preserved_verbatim(self) -> None:
        fragment = '<section class="foo"><h1>Hello &amp; World</h1></section>'
        shell = "A<!-- SPLICE:colophon -->B"
        result = splice(shell, "colophon", fragment)
        assert fragment in result

    def test_surrounding_content_intact(self) -> None:
        shell = "BEFORE<!-- SPLICE:risk_map -->AFTER"
        result = splice(shell, "risk_map", "<div>MAP</div>")
        assert result.startswith("BEFORE")
        assert result.endswith("AFTER")

    def test_empty_fragment_removes_comment(self) -> None:
        shell = "<!-- SPLICE:flow_index -->"
        result = splice(shell, "flow_index", "")
        assert "<!-- SPLICE:" not in result
        assert result == ""


# ---------------------------------------------------------------------------
# load_shell() tests
# ---------------------------------------------------------------------------

class TestLoadShell:
    def test_loads_fixture_as_string(self) -> None:
        content = load_shell(FIXTURE_PATH)
        assert isinstance(content, str)
        assert len(content) > 0

    def test_fixture_contains_all_18_splice_comments(self) -> None:
        content = load_shell(FIXTURE_PATH)
        for placeholder in ALL_PLACEHOLDERS:
            comment = f"<!-- SPLICE:{placeholder} -->"
            assert comment in content, f"Missing SPLICE comment for {placeholder!r}"

    def test_fixture_starts_with_doctype(self) -> None:
        content = load_shell(FIXTURE_PATH)
        assert content.strip().startswith("<!DOCTYPE")

    def test_nonexistent_path_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_shell("/nonexistent/path/shell.html")

    def test_fixture_has_page_div(self) -> None:
        content = load_shell(FIXTURE_PATH)
        assert 'class="page"' in content


# ---------------------------------------------------------------------------
# assemble_brief() tests
# ---------------------------------------------------------------------------

class TestAssembleBrief:
    def test_no_unreplaced_splice_comments_remain(self) -> None:
        """All 18 SPLICE comments must be replaced (by real renders or TODO stubs)."""
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=FIXTURE_PATH)
        assert "<!-- SPLICE:" not in html, (
            "Found unreplaced SPLICE comment in output — "
            "every placeholder must be replaced or stubbed"
        )

    def test_output_is_string(self) -> None:
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=FIXTURE_PATH)
        assert isinstance(html, str)

    def test_doctype_preserved_in_output(self) -> None:
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=FIXTURE_PATH)
        assert html.strip().startswith("<!DOCTYPE")

    def test_page_div_preserved(self) -> None:
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=FIXTURE_PATH)
        assert 'class="page"' in html

    def test_no_todo_stubs_when_all_templates_implemented(self) -> None:
        """Now that all V4 templates are implemented, no TODO stubs should appear."""
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=FIXTURE_PATH)
        # All templates are now implemented — no TODO stubs expected
        assert "<!-- TODO:" not in html

    def test_output_longer_than_input(self) -> None:
        """After splicing, output should be at least as long as input."""
        run_result = _minimal_run_result()
        shell_content = load_shell(FIXTURE_PATH)
        html = assemble_brief(run_result, shell_path=FIXTURE_PATH)
        # TODO stubs are slightly longer than SPLICE comments, so output >= input
        assert len(html) >= len(shell_content)

    def test_accepts_path_object(self) -> None:
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=Path(FIXTURE_PATH))
        assert "<!-- SPLICE:" not in html

    def test_accepts_string_path(self) -> None:
        run_result = _minimal_run_result()
        html = assemble_brief(run_result, shell_path=str(FIXTURE_PATH))
        assert "<!-- SPLICE:" not in html
