"""The voice spec lives in four files. These tests stop them drifting apart.

Until 2026-08-24 the register was defined four separate times — in full in
`editor_v6.txt`, as a prose summary in `editor_v6_friday.txt`, as a paraphrase in
`subeditor_v6.txt` §7, and again in `Master.md` — and the four had already
contradicted each other in production:

* `Master.md` banned humour outright while both prompts allowed "wit is earned,
  not sprinkled", so the sub-editor was told not to flatten a joke the brand
  guide forbade.
* `Master.md` required neutral, diplomatic framing toward BB/NBR/GoB while
  `editor_v6.txt` told the Editor to "puncture the consensus".
* All three prompts announced "four dials" and then listed three, leaving the
  model to invent the fourth.

Nobody noticed for months because nothing compared the files. That is what this
module is for: the shared block must be byte-identical wherever it appears, and
the retired register must not creep back in one file at a time.
"""

from __future__ import annotations

import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROMPTS = _ROOT / "brief" / "claude" / "prompts"

_EDITOR = _PROMPTS / "editor_v6.txt"
_FRIDAY = _PROMPTS / "editor_v6_friday.txt"
_SUBEDITOR = _PROMPTS / "subeditor_v6.txt"
_MASTER = _ROOT / "Master.md"

_VOICE_BEARING_FILES = (_EDITOR, _FRIDAY, _SUBEDITOR, _MASTER)


def _shared_voice_block(path: pathlib.Path) -> str:
    """The `## Voice rules` block, from its heading to whatever follows it.

    The two editor prompts append different material after the block (Mon-Thu
    continues into `## Vintages`, Friday into its week-anchoring addition), so
    the terminator differs by file; the block itself must not.
    """
    text = path.read_text(encoding="utf-8")
    start = text.index("## Voice rules")
    for terminator in ("\n## Vintages", "\n### Friday addition"):
        end = text.find(terminator, start)
        if end != -1:
            return text[start:end].strip()
    raise AssertionError(f"no known terminator after the voice block in {path.name}")


def test_both_editor_prompts_carry_the_identical_voice_block() -> None:
    """One uniform voice means one string, not two descriptions of one string.

    Friday used to *reference* the Mon-Thu rules in prose ("Same as Mon-Thu,
    including the Register calibration block — Economist/FT base, four dials
    ..."). That sentence went stale the moment the real block changed, and it
    described the dials wrongly even before it did.
    """
    assert _shared_voice_block(_EDITOR) == _shared_voice_block(_FRIDAY)


@pytest.mark.parametrize(
    "term",
    [
        "Economist",
        "FT leader",
        "IRREVERENT",
        "four dials",
        "Abdaal",
        "Sinek",
        "Dalio",
        "Welch",
        "Kiyosaki",
    ],
)
def test_the_retired_register_is_gone_from_every_voice_bearing_file(term: str) -> None:
    """Catch a partial revert — the failure mode that produced the drift.

    Each contradiction above came from one file being updated while the others
    kept the old text. Checking all four together is the point.
    """
    offenders = [p.name for p in _VOICE_BEARING_FILES if term in p.read_text(encoding="utf-8")]
    assert offenders == [], f"retired register term {term!r} still present in {offenders}"


@pytest.mark.parametrize("path", [_EDITOR, _FRIDAY])
def test_the_editor_prompts_carry_the_neutrality_clause(path: pathlib.Path) -> None:
    """Neutrality toward BB / NBR / GoB is the owner's non-negotiable."""
    text = path.read_text(encoding="utf-8")
    assert "### Neutrality toward institutions — NON-NEGOTIABLE" in text
    assert "neutral and diplomatic in framing" in text


def test_the_sub_editor_enforces_the_same_neutrality() -> None:
    """A reviewer that does not know the rule cannot catch a breach of it."""
    text = _SUBEDITOR.read_text(encoding="utf-8")
    assert "A JUDGMENT ON AN INSTITUTION" in text
    assert "stay neutral toward institutions" in text


def test_master_md_still_states_the_neutrality_requirement() -> None:
    text = _MASTER.read_text(encoding="utf-8")
    assert "neutral and diplomatic in framing while remaining fact-based in substance" in text


@pytest.mark.parametrize("path", _VOICE_BEARING_FILES)
def test_no_file_reopens_the_humour_allowance(path: pathlib.Path) -> None:
    """`Master.md` said none; the prompts said "wit is earned". None wins now.

    The phrase itself survives in the two files that explicitly WITHDRAW it, so
    this asserts on the permissive framing rather than on the words.
    """
    text = path.read_text(encoding="utf-8")
    assert "wit is earned, not sprinkled:" not in text
    assert "dry wit ONLY where it sharpens" not in text


@pytest.mark.parametrize("path", [_EDITOR, _FRIDAY, _SUBEDITOR])
def test_every_prompt_names_the_daily_star_register(path: pathlib.Path) -> None:
    assert "Daily Star" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [_EDITOR, _FRIDAY])
def test_the_editor_prompts_forbid_carrying_prose_forward(path: pathlib.Path) -> None:
    """Issue 207 measured why the voice change only half-landed.

    `_build_editor_input` used to hand the editor the previous issue with every
    word intact and only the numbers scrubbed. Where the data had not moved,
    the editor restated yesterday's sentence: comparing 206 to 207, `macro`
    came back 100.0% byte-identical, with remit/tbond/iran/fiscal at 94-99%.

    The rule alone was not enough — issue 208 still had `banking` at 97.4%,
    "complying" by nudging "hold 32.26%" to "hold at 32.26%". The input fix
    (`_previous_brief_skeleton`) removes the prose the rule was arguing with,
    and this assertion tracks the wording that describes it.
    """
    text = path.read_text(encoding="utf-8")
    assert "WRITE TODAY'S SENTENCES." in text
    assert "carries none of yesterday's wording" in text


def test_the_sub_editor_catches_carried_forward_prose() -> None:
    """Defence in depth: the reviewer sees the same `previous_brief`.

    Its numbers are blanked but its wording is not, which is precisely the
    signal needed to spot reuse.
    """
    text = _SUBEDITOR.read_text(encoding="utf-8")
    assert "CARRIED-FORWARD PROSE." in text
    assert "compare the WORDING" in text


def test_the_sub_editor_rule_count_matches_the_editor_rules() -> None:
    """The off-by-one that started all of this.

    All three prompts once announced "four dials" and listed three, leaving the
    model to invent the fourth. The sub-editor summarises the editor's register
    rules by COUNT, so adding a rule to the editors without updating that count
    reintroduces exactly that bug.
    """
    block = _shared_voice_block(_EDITOR)
    register = block[block.index("### Register") : block.index("### Neutrality")]
    editor_rules = sum(1 for line in register.splitlines() if line.startswith("- "))
    assert editor_rules == 4, "register bullets changed; update the sub-editor's count"
    assert "held to five rules over that base" in _SUBEDITOR.read_text(encoding="utf-8")
