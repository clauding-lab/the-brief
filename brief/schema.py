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


BankerReadInsight = Annotated[
    Union[BankerReadStructured, BankerReadFreeform],
    Field(discriminator="kind"),
]


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


class ExecSignal(BaseModel):
    direction: SignalKind
    text: str = Field(..., max_length=200)
    section_anchor: str


class SectionData(BaseModel):
    id: str
    title: str
    metrics: list[Metric] = Field(default_factory=list)
    news: list[NewsItem] = Field(default_factory=list)
    freshness: FreshnessKind
    freshness_reason: Optional[str] = None
    bankerread: Optional[BankerReadInsight] = None
    exec_signals: Optional[list[ExecSignal]] = None
    pull: str | None = None
    degraded_breadth: bool = False
    degraded_sector_heat: bool = False
    extras: dict = Field(default_factory=dict)
