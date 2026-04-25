"""Pydantic data contracts for The Brief."""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

CadenceKind = Literal["daily", "weekly", "monthly", "quarterly", "event"]
FreshnessKind = Literal["fresh", "warning", "stale", "pending", "unavailable", "warming_up"]
DirectionKind = Literal["up", "down", "flat"]
SignalKind = Literal["bull", "bear", "warn", "watch"]
DeltaWindow = Literal["dod", "wow", "mom", "yoy"]


class Delta(BaseModel):
    value: float
    direction: DirectionKind
    window: DeltaWindow


class Metric(BaseModel):
    id: str
    label: str
    value: float | int | str | None
    unit: str
    as_of: date
    source: str
    source_url: Optional[str] = None
    cadence: CadenceKind
    delta: Optional[Delta] = None
    hero: bool = False


class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published: datetime


class BankerReadStructured(BaseModel):
    kind: Literal["structured"] = "structured"
    meaning: str
    action: str
    trigger: str
    focus: str
    pull: str


class BankerReadFreeform(BaseModel):
    kind: Literal["freeform"] = "freeform"
    text: str
    pull: str | None = None


# V4 legacy discriminated union — kept for back-compat with V4 templates and tests.
BankerReadUnion = Annotated[
    Union[BankerReadStructured, BankerReadFreeform],
    Field(discriminator="kind"),
]

# Backward-compat alias so any existing import of BankerReadInsight as the
# discriminated union still works at the TypeAdapter level.  The new
# BankerReadInsight *class* is defined below and shadows this at module level;
# code that does `from brief.schema import BankerReadInsight` will get the
# class.  Code that used the union as a type annotation should migrate to
# BankerReadUnion.
_BankerReadLegacyUnion = BankerReadUnion


class BankerReadInsight(BaseModel):
    """Banker's read insight, multi-variant.

    V5 path: variant in {"full", "stale_micro"} with structured fields.
    V4 path: variant == "v4_legacy" with `sentences: list[str]`.
    Templates branch on `variant`.
    """
    sentences: list[str] | None = None
    meaning: str | None = None
    action: str | None = None
    trigger: str | None = None
    focus: str | None = None
    pull_quote: str | None = None
    generated_at: datetime
    variant: Literal["full", "stale_micro", "v4_legacy"] = "full"


class MapCoord(BaseModel):
    section_id: str
    x: float = Field(ge=0, le=10)
    y: float = Field(ge=0, le=10)
    r: int = Field(ge=20, le=50)
    type: Literal["event", "fresh", "slow", "anchor"]
    hero_metric_id: str | None = None


class TodaysCall(BaseModel):
    text: str = Field(max_length=400)
    byline: str = "Desk Editor · The Brief"
    generated_at: datetime | None = None


class ExecSignal(BaseModel):
    direction: SignalKind
    text: str = Field(..., max_length=200)
    section_anchor: str


class SectionData(BaseModel):
    id: str
    title: str
    kicker: str = ""             # V5 — back-compat default empty
    tldr: str = ""               # V5 — back-compat default empty
    metrics: list[Metric] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    freshness: FreshnessKind
    freshness_reason: Optional[str] = None
    # Accept V5 BankerReadInsight, V4 BankerReadStructured, or V4 BankerReadFreeform
    bankerread: Optional[Union[BankerReadInsight, BankerReadStructured, BankerReadFreeform]] = None
    exec_signals: Optional[list[ExecSignal]] = None
    pull: str | None = None
    degraded_breadth: bool = False
    degraded_sector_heat: bool = False
    extras: dict = Field(default_factory=dict)
    systemic_risk: Optional["SystemicRisk"] = None  # V5
    risk_active: bool = False                        # V5
    history_values: list[float] | None = None        # V5


# ---------------------------------------------------------------------------
# V5 new types
# ---------------------------------------------------------------------------

class SystemicRisk(BaseModel):
    headline: str
    body: str
    level: Literal["warning", "critical"]
    rule_id: str  # which deterministic rule fired (e.g. "banking_npl_above_30")


class MapPoint(BaseModel):
    id: str
    x: float
    y: float
    r: float
    kind: Literal["event", "fresh", "slow", "anchor"]


class GridEntry(BaseModel):
    id: str
    tldr: str  # ≤ 12 words; validator at validator-layer enforces


class TopPicks(BaseModel):
    plotted: list[MapPoint]
    grid: list[GridEntry]
    front_of_book_id: str


class QAIssue(BaseModel):
    section_id: str | None = None
    severity: Literal["info", "warn", "block"]
    message: str


class EditorialQAResult(BaseModel):
    status: Literal["pass", "block"]
    issues: list[QAIssue] = []
    shippable: bool


# Resolve forward reference for SectionData.systemic_risk
SectionData.model_rebuild()
