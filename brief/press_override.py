"""Owner-approved press overrides: carry the press source onto the card.

EconDelta's `_apply_media_overrides` (aggregate_latest.py) re-asserts a human-approved press
figure into `metric_history` after the normal upsert, with row source
`media-approved:<outlet>` (<outlet> = media_review.source_outlet, or "press" when absent).
Owner decision (c), 26 Sep 2026 BDT: such a figure is the press's, so the card says
"via The Daily Star (approved)" and never "BB".

The outlet slug -> name mapping is explicit. A slug with no entry is shown verbatim: an
unmapped outlet is never given a guessed publication name.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brief.history import HistoryRow

MEDIA_APPROVED_PREFIX = "media-approved:"
# EconDelta scrapers/media_screen.py `_OUTLET_SOURCES` / `_outlet_of` slugs.
_OUTLET_NAMES: dict[str, str] = {
    "thedailystar": "The Daily Star",
    "tbsnews": "The Business Standard",  # tbsnews.net
}
_CARD_PREFIX, _CARD_SUFFIX = "via ", " (approved)"


@dataclass(frozen=True)
class PressOverride:
    """The media-approved history row a builder printed: its outlet slug, value and date."""

    outlet: str
    value: float
    as_of: date

    @property
    def card_source(self) -> str:
        return card_source(self.outlet)


def press_override(row: HistoryRow | None) -> PressOverride | None:
    """The approved press figure `row` carries, or None for any other row."""
    source = getattr(row, "source", None)
    if row is None or not isinstance(source, str) or not source.startswith(MEDIA_APPROVED_PREFIX):
        return None
    # An empty slug takes EconDelta's own label for an outlet-less override ("press").
    outlet = source[len(MEDIA_APPROVED_PREFIX):] or "press"
    return PressOverride(outlet=outlet, value=row.value, as_of=row.as_of)


def outlet_name(outlet: str) -> str:
    """The publication name for `outlet`, or the slug itself when it has no explicit name."""
    return _OUTLET_NAMES.get(outlet, outlet)


def card_source(outlet: str) -> str:
    """The card source line for an approved figure from `outlet`."""
    return f"{_CARD_PREFIX}{outlet_name(outlet)}{_CARD_SUFFIX}"


def is_press_card_source(source: Any) -> bool:
    """True for a source line `card_source` produced."""
    return (isinstance(source, str) and source.startswith(_CARD_PREFIX)
            and source.endswith(_CARD_SUFFIX) and len(source) > len(_CARD_PREFIX + _CARD_SUFFIX))
