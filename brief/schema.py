"""Pydantic data contracts for The Brief."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

CadenceKind = Literal["daily", "weekly", "monthly", "quarterly", "event"]
FreshnessKind = Literal["fresh", "warning", "stale", "pending", "unavailable"]
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


class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published: datetime


class BankerReadInsight(BaseModel):
    sentences: list[str]
    generated_at: datetime
    variant: Literal["full", "stale_micro"] = "full"


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
