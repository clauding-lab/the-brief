"""V6 brief Pydantic models — mirror of types/brief.ts in the Next.js app.

Used to validate the JSON output of editor_v6.txt and subeditor_v6.txt prompts
before publishing to Supabase. Strict — extra fields are rejected so prompt
drift surfaces as a validation error, not silent breakage downstream.
"""
from __future__ import annotations

from datetime import date as date_t
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Tone = Literal["bull", "bear", "warn", "neu"]
SectionGroup = Literal["overview", "banking", "markets", "realeco", "policy"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CoverMetricV6(_Strict):
    label: str
    value: str
    sub: Optional[str] = None
    tone: Optional[Tone] = None
    section_slug: Optional[str] = None
    as_of: Optional[str] = None


class BriefV6(_Strict):
    issue_no: int = Field(ge=1)
    volume: int = Field(ge=1)
    brief_date: date_t
    read_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    cover_metric: Optional[CoverMetricV6] = None
    todays_call: Optional[str] = None
    status: Optional[Literal["draft", "published", "archived"]] = "published"


class MetricV6(_Strict):
    label: str
    value: str
    sub: Optional[str] = None
    tone: Optional[Tone] = None
    is_snapshot: Optional[bool] = False
    spark: Optional[list[float]] = None
    delta: Optional[str] = None
    delta_pct: Optional[str] = None
    changed: Optional[bool] = False
    weight: Optional[int] = Field(default=1, ge=1, le=2)


class NewsItemV6(_Strict):
    headline: str
    detail: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    tone: Optional[Tone] = None
    changed: Optional[bool] = False


class SeriesPointV6(_Strict):
    key: Optional[str] = None
    ts: str  # YYYY-MM-DD
    value: float


class SeriesNoteV6(_Strict):
    series_key: str
    ts: str
    label: str
    detail: Optional[str] = None


class SummaryPillV6(_Strict):
    key: str
    value: str
    tone: Optional[Tone] = "neu"


class RunwayV6(_Strict):
    value: str
    unit: str


class BankerReadV6(_Strict):
    verdict: str = Field(min_length=20, max_length=400)
    watch: list[str] = Field(default_factory=list, max_length=4)
    risk: list[str] = Field(default_factory=list, max_length=4)
    runway: Optional[RunwayV6] = None


class SectionV6(_Strict):
    slug: str
    ord: int = Field(ge=1, le=18)
    title: str
    group_key: SectionGroup
    verdict: Optional[str] = None
    verdict_tone: Optional[Tone] = None
    banker_read: Optional[BankerReadV6] = None
    weight: int = Field(default=1, ge=1, le=2)
    tldr: Optional[str] = None
    summary_pills: list[SummaryPillV6] = Field(default_factory=list, max_length=6)
    analysis: Optional[str] = None
    metrics: list[MetricV6] = Field(default_factory=list)
    news: list[NewsItemV6] = Field(default_factory=list)
    series: list[SeriesPointV6] = Field(default_factory=list)
    notes: list[SeriesNoteV6] = Field(default_factory=list)


class BriefPayloadV6(_Strict):
    """Full output of the editor mega-prompt — what the publisher writes to Supabase."""

    brief: BriefV6
    sections: list[SectionV6] = Field(min_length=1, max_length=18)


# ─── Subeditor review output ─────────────────────────────────────────────

ReviewVerdict = Literal["pass", "revise", "fail"]
IssueSeverity = Literal["warn", "error"]


class ReviewIssue(_Strict):
    section: Optional[str] = None  # null = brief-level (cover, todays_call)
    field: str
    severity: IssueSeverity
    problem: str = Field(min_length=10)


class SubeditorReview(_Strict):
    verdict: ReviewVerdict
    issues: list[ReviewIssue] = Field(default_factory=list)
    revised_brief: Optional[BriefPayloadV6] = None
