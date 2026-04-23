"""Registry for section builders.

Spine = must ship daily; graceful-stale allowed but never dropped.
Keep  = useful context; may degrade silently to last-known or unavailable.
"""
from __future__ import annotations

SPINE_BUILDER_IDS: tuple[str, ...] = (
    "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
    "headlines", "exec",
)

KEEP_BUILDER_IDS: tuple[str, ...] = ("comm", "banking", "dam", "fiscal", "nbr")

ALL_BUILDER_IDS: tuple[str, ...] = SPINE_BUILDER_IDS + KEEP_BUILDER_IDS

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Optional, Sequence

if TYPE_CHECKING:
    from brief.econdelta import EconDeltaSnapshot
    from brief.history import MetricHistoryClient
    from brief.headlines import Headline


@dataclass(frozen=True)
class BuilderContext:
    snapshot: "EconDeltaSnapshot"
    history: Optional["MetricHistoryClient"]
    today: date
    headlines: Sequence["Headline"] = ()
    claude_outputs: dict[str, Any] = field(default_factory=dict)
