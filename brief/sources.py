"""Headline source taxonomy — colored lozenge badges per outlet.

Outlets are keyed by short code (REU, DS, TBS, FE, BBC, AJZ, FT, BBN). The
resolver also accepts common display names (case-insensitive), so existing
data flows that populate `NewsItem.source` with a long name still resolve
to the right badge.

Add new outlets here; the render layer pulls colors from `_NAME_TO_CSS`
classes defined in `brief/render/v5/styles.css`.
"""
from __future__ import annotations

from typing import Final

SOURCE_BADGES: Final[dict[str, dict[str, str]]] = {
    "REU": {"name": "Reuters",                "css": "reu"},  # red bg
    "DS":  {"name": "The Daily Star",         "css": "ds"},   # black
    "TBS": {"name": "The Business Standard",  "css": "tbs"},  # black
    "FE":  {"name": "Financial Express",      "css": "fe"},   # black
    "BBC": {"name": "BBC",                    "css": "bbc"},  # white w/ black border
    "AJZ": {"name": "Al Jazeera",             "css": "ajz"},  # black w/ amber accent
    "FT":  {"name": "Financial Times",        "css": "ft"},   # FT salmon
    "BBN": {"name": "BB News",                "css": "bbn"},  # oxblood
}


_NAME_ALIASES: Final[dict[str, str]] = {
    # canonical names (lowercased)
    **{v["name"].casefold(): k for k, v in SOURCE_BADGES.items()},
    # common variants seen in scrapers
    "tbs news":              "TBS",
    "financial express bd":  "FE",
    "financial-express":     "FE",
    "daily star":            "DS",
    "thedailystar":          "DS",
    "reuter":                "REU",
}


def resolve_source_code(s: str | None) -> str | None:
    """Resolve a source code or display name to a SOURCE_BADGES key.

    Returns None for unknown sources or empty input.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    if s in SOURCE_BADGES:
        return s
    return _NAME_ALIASES.get(s.casefold())
