"""Splice per-section JSX into the-brief.html shell.

The shell contains `function SectionXxx() { ... }` definitions inside a
<script type="text/babel"> block. We locate each by name, find the
balanced `{...}` body, and substitute a freshly-rendered full function.
"""
from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_log = logging.getLogger(__name__)


# Chars that can immediately precede a string literal in valid JS/JSX context.
# Excludes `<` and `>` (JSX tag ambiguity) and alphanumerics (apostrophe-in-text).
# `return "x"` etc. is safe even without a keyword check: the heuristic skips the
# quotes entirely, treating them as literal chars — the contents of "x" don't
# affect brace depth so no harm done.
_EXPR_START_CHARS = frozenset("([{,;=+-*/%^&|~!?:")


def _brace_end(text: str, start: int) -> int:
    """Return index of the `}` closing the `{` at `start`.

    Heuristic JS+JSX lexer: tracks string literals (`"`, `'`, `` ` ``) but only
    enters string mode when the quote is in a JS expression-start position. JSX
    text content like `Rahman's promised...` is correctly skipped because the
    `'` is preceded by an alphabetic character (not a JS expression starter).
    Limitation: doesn't handle `return "x"` style keyword-prefix strings as
    strings — but their contents don't affect brace depth, so this is benign.
    A full JS+JSX lexer (acorn-style) would be more robust for edge cases.
    """
    depth = 0
    in_str: str | None = None
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                # Look back past whitespace for context.
                j = i - 1
                while j >= start and text[j] in (" ", "\t", "\n", "\r"):
                    j -= 1
                if j < start or text[j] in _EXPR_START_CHARS:
                    in_str = ch
                # else: apostrophe/quote in text content; ignore.
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return len(text) - 1


def _find_function(text: str, name: str) -> tuple[int, int] | None:
    """Locate a zero-argument `function NAME() { ... }` definition.

    Only matches zero-arg signatures by design — Sections in the shell are all
    zero-arg components. Functions with destructured props (e.g.
    `MetricCard({label, value})`) are intentionally not matched.
    """
    m = re.search(r"function\s+" + re.escape(name) + r"\s*\(\s*\)", text)
    if not m:
        return None
    brace = text.find("{", m.end())
    if brace == -1:
        return None
    end = _brace_end(text, brace)
    return m.start(), end + 1


def replace_function_body(text: str, name: str, new_function: str) -> str:
    span = _find_function(text, name)
    if span is None:
        return text
    start, end = span
    return text[:start] + new_function + text[end:]


def remove_function(text: str, name: str) -> str:
    span = _find_function(text, name)
    if span is not None:
        start, end = span
        text = text[:start] + text[end:]
    # Also drop self-closing usage like <SectionRMG />
    text = re.sub(r"<\s*" + re.escape(name) + r"\s*/\s*>", "", text)
    # And paired <SectionRMG>…</SectionRMG> (defensive; not expected in this shell)
    text = re.sub(
        r"<\s*" + re.escape(name) + r"[^>]*>.*?<\s*/\s*" + re.escape(name) + r"\s*>",
        "", text, flags=re.DOTALL,
    )
    return text


@dataclass
class Shell:
    text: str

    @classmethod
    def load(cls, path: Path | str) -> "Shell":
        return cls(text=Path(path).read_text(encoding="utf-8"))

    def replace(self, name: str, new_function: str) -> None:
        self.text = replace_function_body(self.text, name, new_function)

    def remove_cut_sections(self, names: Iterable[str]) -> None:
        for n in names:
            self.text = remove_function(self.text, n)

    def write(self, path: Path | str) -> None:
        Path(path).write_text(self.text, encoding="utf-8")


from brief.schema import SectionData as _SectionData


_SECTION_TO_TEMPLATE: dict[str, tuple[str, str]] = {
    # section id -> (template module, React component name to replace)
    "bb":         ("brief.render.templates.section_bb",         "SectionBB"),
    "macro":      ("brief.render.templates.section_macro",      "SectionMacro"),
    "fx":         ("brief.render.templates.section_fx",         "SectionFX"),
    "remit":      ("brief.render.templates.section_remittance", "SectionRemittance"),
    "dse":        ("brief.render.templates.section_dse",        "SectionDSE"),
    "tbond":      ("brief.render.templates.section_tbond",      "SectionTBond"),
    "iranwar":    ("brief.render.templates.section_iranwar",    "SectionIranWar"),
    "headlines":  ("brief.render.templates.section_headlines",  "SectionHeadlines"),
    "exec":       ("brief.render.templates.section_exec",       "SectionExec"),
    "comm":       ("brief.render.templates.section_comm",       "SectionComm"),
    "banking":    ("brief.render.templates.section_banking",    "SectionBanking"),
    "dam":        ("brief.render.templates.section_dam",        "SectionDAM"),
    "fiscal":     ("brief.render.templates.section_fiscal",     "SectionFiscal"),
    "nbr":        ("brief.render.templates.section_nbr",        "SectionNBR"),
}

CUT_SECTIONS = ("SectionRMG", "SectionPower", "SectionPeers")


def assemble_brief(
    shell_path: Path | str,
    sections: Iterable[_SectionData],
) -> str:
    shell = Shell.load(shell_path)
    for section in sections:
        mapping = _SECTION_TO_TEMPLATE.get(section.id)
        if mapping is None:
            _log.warning("section %r has no template registered; skipping", section.id)
            continue
        mod_name, component_name = mapping
        mod = importlib.import_module(mod_name)
        new_body = mod.render(section)
        shell.replace(component_name, new_body)
    shell.remove_cut_sections(CUT_SECTIONS)
    return shell.text
