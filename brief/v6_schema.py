"""V6 brief Pydantic models — mirror of types/brief.ts in the Next.js app.

Used to validate the JSON output of editor_v6.txt and subeditor_v6.txt prompts
before publishing to Supabase. Strict — extra fields are rejected so prompt
drift surfaces as a validation error, not silent breakage downstream.
"""
from __future__ import annotations

from datetime import date as date_t
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Tone = Literal["bull", "bear", "warn", "neu"]
SectionGroup = Literal["overview", "banking", "markets", "realeco", "policy"]
FreshnessKind = Literal["fresh", "warning", "stale", "unavailable", "warming_up"]


class _Strict(BaseModel):
    """Top-level structure — extra fields rejected (catches prompt drift)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Lenient(BaseModel):
    """Row-level data — extras silently dropped.

    The editor naturally passes through fields from V5 raw input (as_of, source,
    history_values, etc.) that the V6 Supabase tables don't have. Drop them at
    validate-time so model_dump() emits only Supabase-known columns.
    """
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class CoverMetricV6(_Lenient):
    label: str
    value: str
    sub: Optional[str] = None
    tone: Optional[Tone] = None
    section_slug: Optional[str] = None
    as_of: Optional[str] = None
    held_from: Optional[date_t] = None
    next_print: Optional[str] = None


class BriefV6(_Strict):
    issue_no: int = Field(ge=1)
    volume: int = Field(ge=1)
    brief_date: date_t
    read_minutes: Optional[int] = Field(default=None, ge=1, le=120)
    cover_metric: Optional[CoverMetricV6] = None
    todays_call: Optional[str] = None
    status: Optional[Literal["draft", "published", "archived"]] = "published"
    lens: Optional[str] = None
    frame: Optional[str] = None


def _stringify_numeric(v: Any) -> Any:
    """Coerce int/float to str without forcing precision; pass strings through.

    The v1.4.0 banker-grade editor occasionally emits metric `value` and `delta`
    fields as raw numbers (e.g., `35.1112`) where the schema previously required
    pre-formatted strings (e.g., `"$35.11B"`). Stringify so the publish doesn't
    crash; SPA display is best-effort. Prompt-side cleanup is the proper fix.
    """
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):  # bool is a subclass of int; treat as literal
        return str(v)
    if isinstance(v, (int, float)):
        # f"{x:.10g}" trims trailing zeros while preserving genuine precision
        return f"{v:.10g}"
    return v


def _stringify_delta(v: Any) -> Any:
    """Stringify a delta field that may arrive as a structured dict.

    The editor sometimes emits delta as `{value, direction, window}` rather
    than a banker-formatted string. Render dicts as "+0.99% WoW" / "−0.99% WoW".
    Plain numerics use `_stringify_numeric`. None and strings pass through.
    """
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, dict):
        raw = v.get("value")
        direction = (v.get("direction") or "").lower()
        window = (v.get("window") or "").upper()
        if raw is None:
            return ""
        try:
            num = float(raw)
        except (TypeError, ValueError):
            return str(raw)
        sign = "+" if direction == "up" else ("−" if direction == "down" else "")
        magnitude = f"{abs(num):.2f}%"
        window_pretty = {
            "DOD": "DoD", "WOW": "WoW", "MOM": "MoM",
            "YOY": "YoY", "QOQ": "QoQ",
        }.get(window, window)
        return f"{sign}{magnitude} {window_pretty}".strip()
    return _stringify_numeric(v)


class MetricV6(_Lenient):
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
    held_from: Optional[date_t] = None
    next_print: Optional[str] = None

    @field_validator("value", "delta_pct", mode="before")
    @classmethod
    def _coerce_value(cls, v: Any) -> Any:
        return _stringify_numeric(v)

    @field_validator("delta", mode="before")
    @classmethod
    def _coerce_delta(cls, v: Any) -> Any:
        return _stringify_delta(v)


class NewsItemV6(_Lenient):
    headline: str
    detail: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[str] = None
    tone: Optional[Tone] = None
    changed: Optional[bool] = False
    held_from: Optional[date_t] = None


class MoverRowV6(_Lenient):
    """F4 — one DS30 blue-chip mover: ticker, latest close (taka), 1-month return %."""
    ticker: str = Field(min_length=1)
    price: float
    return_pct: float


class SeriesPointV6(_Lenient):
    key: Optional[str] = None
    ts: str  # YYYY-MM-DD
    value: float


class SeriesNoteV6(_Lenient):
    series_key: str
    ts: str
    label: str
    detail: Optional[str] = None


class SummaryPillV6(_Lenient):
    key: str
    value: str
    tone: Optional[Tone] = "neu"


class RunwayV6(_Strict):
    value: str
    unit: str


class BankerReadV6(_Strict):
    # 400 -> 1000 with the Daily Star voice change. Full sentences cost roughly
    # 50% more characters than the telegraphic register they replace (a live
    # issue-206 verdict went 231 -> 355 chars on rewrite), and a verdict that
    # overruns this cap fails validation and holds the whole publish. This is a
    # SAFETY limit, not a target: the length the Editor actually aims for is the
    # "150-450 chars" in editor_v6.txt, and the SPA renders this field at 22px
    # (30px in the hero), so a genuinely 1000-char verdict would be a wall of
    # display type. The headroom exists so a good verdict is never truncated —
    # not so the desk can write essays.
    verdict: str = Field(min_length=20, max_length=1000)
    watch: list[str] = Field(default_factory=list, max_length=4)
    risk: list[str] = Field(default_factory=list, max_length=4)
    runway: Optional[RunwayV6] = None


class ChartReadV6(_Strict):
    """Pre-rendered interpretive read under a section's chart card (v1.4.0)."""

    signal: str = Field(min_length=1)
    context: str = Field(min_length=1)
    implication: str = Field(min_length=1)


class SectionV6(_Strict):
    slug: str
    ord: int = Field(ge=1, le=18)
    title: str
    group_key: SectionGroup
    freshness: Optional[FreshnessKind] = None
    verdict: Optional[str] = None
    verdict_tone: Optional[Tone] = None
    banker_read: Optional[BankerReadV6] = None
    weight: int = Field(default=1, ge=1, le=2)
    tldr: Optional[str] = None
    summary_pills: list[SummaryPillV6] = Field(default_factory=list, max_length=6)
    analysis: Optional[str] = None
    chart_read: Optional[ChartReadV6] = None
    movers: Optional[list[MoverRowV6]] = None
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

    @model_validator(mode="after")
    def _revise_requires_brief(self) -> "SubeditorReview":
        """A review gate must never fail OPEN (AGENT_LEARNINGS.md): verdict="revise"
        without a revised_brief previously validated cleanly and shipped the
        unrevised editor brief while the publish log claimed the sub-editor
        passed. Reject it here so the caller's malformed-review retry-then-hold
        path (pipeline_v6._run_subeditor) catches it instead."""
        if self.verdict == "revise" and self.revised_brief is None:
            raise ValueError(
                'verdict="revise" requires revised_brief — got None'
            )
        return self
