"""Registry for section builders.

Spine = must ship daily; graceful-stale allowed but never dropped.
Keep  = useful context; may degrade silently to last-known or unavailable.
"""
from __future__ import annotations

# v1.6.7 dropped "comm" (Commodities). Its two tiles were Gold and LNG; LNG's
# only live series is a monthly Pink Sheet print that had been dead 105 days
# before v1.6.6 repointed it, and Gold now lives in `fx` as a reserve-asset
# reading. A one-tile section is not a section.
SPINE_BUILDER_IDS: tuple[str, ...] = (
    "bb", "macro", "fx", "dse", "tbond", "iranwar",
    "headlines", "exec",
    "fiscal", "remit",
)

KEEP_BUILDER_IDS: tuple[str, ...] = ("banking",)

ALL_BUILDER_IDS: tuple[str, ...] = SPINE_BUILDER_IDS + KEEP_BUILDER_IDS

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Mapping, Sequence

if TYPE_CHECKING:
    from brief.econdelta import EconDeltaSnapshot
    from brief.history import MetricHistoryClient
    from brief.headlines import Headline


@dataclass(frozen=True)
class BuilderContext:
    snapshot: EconDeltaSnapshot
    history: MetricHistoryClient | None
    today: date
    headlines: Sequence[Headline] = ()
    claude_outputs: Mapping[str, Any] = field(default_factory=dict)
    # v1.4.0 — same client as `history` but callers pass
    # table="metric_history_monthly" per call. Separate field so builders that
    # don't need monthly data don't need to be updated.
    history_monthly: "MetricHistoryClient | None" = None
