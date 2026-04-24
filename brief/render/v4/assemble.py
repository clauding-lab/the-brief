"""V4 shell splicer — replaces HTML comments like <!-- SPLICE:name --> with fragments.

Much simpler than Part 1's brace-counting approach since the shell is a clean template.
All V4 code is isolated under brief/render/v4/ to avoid touching Part 1 render code
(which remains at brief/render/assemble.py) while tests transition.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brief.pipeline import RunResult

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------

class AssembleError(Exception):
    """Raised when a SPLICE placeholder is missing or ambiguous in the shell."""


# ---------------------------------------------------------------------------
# Shell loader
# ---------------------------------------------------------------------------

def load_shell(path: str | Path) -> str:
    """Read the shell HTML template from disk and return as a string."""
    return Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Splice engine
# ---------------------------------------------------------------------------

def splice(shell: str, placeholder: str, fragment_html: str) -> str:
    """Replace <!-- SPLICE:{placeholder} --> with fragment_html.

    Raises AssembleError if the placeholder is not found or appears more than once.
    """
    pattern = f"<!-- SPLICE:{placeholder} -->"
    count = shell.count(pattern)
    if count != 1:
        raise AssembleError(
            f"placeholder {placeholder!r} not found or ambiguous "
            f"(found {count} occurrences in shell)"
        )
    return shell.replace(pattern, fragment_html, 1)


# ---------------------------------------------------------------------------
# Placeholder → renderer mapping
# ---------------------------------------------------------------------------

_PLACEHOLDER_TO_RENDERER: dict[str, tuple[str, str]] = {
    "dateline":           ("brief.render.v4.templates.dateline",          "render_dateline"),
    "masthead_todays_call": ("brief.render.v4.templates.masthead",         "render_masthead"),
    "risk_map":           ("brief.render.v4.templates.risk_map",           "render_risk_map"),
    "flow_index":         ("brief.render.v4.templates.flow_index",         "render_flow_index"),
    "section_headlines":  ("brief.render.v4.templates.section_headlines",  "render_section_headlines"),
    "section_bb":         ("brief.render.v4.templates.section_bb",         "render_section_bb"),
    "section_banking":    ("brief.render.v4.templates.section_banking",    "render_section_banking"),
    "section_dse":        ("brief.render.v4.templates.section_dse",        "render_section_dse"),
    "section_tbond":      ("brief.render.v4.templates.section_tbond",      "render_section_tbond"),
    "section_fx":         ("brief.render.v4.templates.section_fx",         "render_section_fx"),
    "section_macro":      ("brief.render.v4.templates.section_macro",      "render_section_macro"),
    "section_dam":        ("brief.render.v4.templates.section_dam",        "render_section_dam"),
    "section_comm":       ("brief.render.v4.templates.section_comm",       "render_section_comm"),
    "section_remit":      ("brief.render.v4.templates.section_remit",      "render_section_remit"),
    "section_iranwar":    ("brief.render.v4.templates.section_iranwar",    "render_section_iranwar"),
    "section_fiscal":     ("brief.render.v4.templates.section_fiscal",     "render_section_fiscal"),
    "section_nbr":        ("brief.render.v4.templates.section_nbr",        "render_section_nbr"),
    "colophon":           ("brief.render.v4.templates.colophon",           "render_colophon"),
}


# ---------------------------------------------------------------------------
# Assembler orchestrator
# ---------------------------------------------------------------------------

def assemble_brief(
    run_result: "RunResult",
    shell_path: str | Path | None = None,
) -> str:
    """Orchestrate: load shell → render each block → splice → return full HTML.

    Template functions are imported lazily from brief.render.v4.templates.*
    to avoid circular imports and to let this function work even before all
    templates are implemented (templates that are not yet written produce a
    TODO comment in the output instead of aborting the pipeline).

    Parameters
    ----------
    run_result:
        The pipeline RunResult supplying sections, map_coords, todays_call, etc.
    shell_path:
        Optional override for the shell HTML path.
        Defaults to brief/render/v4/shell_v4.html relative to this file.
    """
    if shell_path is None:
        shell_path = Path(__file__).parent / "shell_v4.html"

    html = load_shell(shell_path)

    for placeholder, (module_path, func_name) in _PLACEHOLDER_TO_RENDERER.items():
        try:
            mod = importlib.import_module(module_path)
            renderer = getattr(mod, func_name)
            fragment = renderer(run_result)
        except ModuleNotFoundError:
            _log.debug(
                "V4 template %s not yet implemented; inserting TODO stub for %r",
                module_path,
                placeholder,
            )
            fragment = f"<!-- TODO: {placeholder} renderer not yet implemented -->"
        except AttributeError as exc:
            _log.warning(
                "V4 template %s missing function %s: %s",
                module_path,
                func_name,
                exc,
            )
            fragment = f"<!-- TODO: {placeholder} renderer not yet implemented -->"
        except Exception as exc:  # noqa: BLE001
            _log.error(
                "V4 renderer %s.%s raised %r; falling back to stub",
                module_path,
                func_name,
                exc,
            )
            fragment = f"<!-- TODO: {placeholder} renderer failed: {exc} -->"

        try:
            html = splice(html, placeholder, fragment)
        except AssembleError as exc:
            _log.error("AssembleError for placeholder %r: %s", placeholder, exc)
            # Continue — the unreplaced comment is better than a crash.

    return html
