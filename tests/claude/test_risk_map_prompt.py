"""Tests that the risk_map_layout prompt file is internally consistent.

The prompt must instruct Claude to return exactly 12 sections — matching the
12 sections that _risk_map_sections() passes after filtering out 'exec' and
'headlines'.  Before the fix the file said "14" in four places, causing Claude
to hallucinate two extra sections to fill the quota.
"""
import re
from pathlib import Path

PROMPT_PATH = (
    Path(__file__).parent.parent.parent
    / "brief" / "claude" / "prompts" / "risk_map_layout.txt"
)


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def test_prompt_file_exists():
    assert PROMPT_PATH.exists(), f"Prompt file not found: {PROMPT_PATH}"


def test_prompt_says_12_not_14_for_section_count():
    """Prompt must not contain any count-context mention of '14'.

    Any occurrence of the bare number 14 in a count sentence (e.g.
    'exactly 14', '14 entries', '14 sections') is wrong — the input
    has 12 sections after exec and headlines are filtered out.
    """
    text = _load_prompt()
    # Find every word-boundary occurrence of '14'
    occurrences = [(m.start(), text[max(0, m.start() - 40):m.end() + 40])
                   for m in re.finditer(r'\b14\b', text)]
    assert occurrences == [], (
        f"Prompt still contains '14' in {len(occurrences)} place(s):\n"
        + "\n".join(f"  pos {pos}: ...{ctx}..." for pos, ctx in occurrences)
    )


def test_prompt_contains_exactly_12_in_count_context():
    """Prompt must explicitly say '12' when specifying the section count."""
    text = _load_prompt()
    assert re.search(r'\b12\b', text), (
        "Prompt does not contain '12' — expected at least one count-context reference."
    )


def test_prompt_read_order_says_12():
    """The READ ORDER RULE section must reference 12 section_ids, not 14."""
    text = _load_prompt()
    # The read_order rule line should contain '12'
    read_order_block = [
        line for line in text.splitlines()
        if "read_order" in line.lower() and re.search(r'\b1[24]\b', line)
    ]
    for line in read_order_block:
        assert re.search(r'\b12\b', line), (
            f"read_order rule line still references wrong count: {line!r}"
        )
