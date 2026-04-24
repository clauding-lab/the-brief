"""Splice per-section JSX into the-brief.html shell.

The shell contains `function SectionXxx() { ... }` definitions inside a
<script type="text/babel"> block. We locate each by name, find the
balanced `{...}` body, and substitute a freshly-rendered full function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _brace_end(text: str, start: int) -> int:
    """Return index of the `}` closing the `{` at `start`. Ported from update.py."""
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
                in_str = ch
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
