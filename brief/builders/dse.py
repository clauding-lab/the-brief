"""Builder: DSE daily market snapshot."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

from brief.cadence import is_bd_trading_day, section_freshness
from brief.history import HttpClient, UrllibHttp
from brief.schema import Metric, SectionData
from . import BuilderContext


_log = logging.getLogger(__name__)

# Column 0 (mid) is the DISPLAY metric id (prev-brief diff continuity + SPA
# keys) — it stays `dse_`-prefixed and is NOT queried by THIS builder's
# fallback. (pipeline._enrich_metric_history still batches every Metric.id
# into a metric_history window query, where these six match nothing — that
# path feeds Metric.history_values, which V6 drops before publish, so it is
# inert today but is NOT an invariant.)
# Column 2 (src_key) is the LIVE id EconDelta actually writes, both to the
# snapshot dict AND to metric_history, and is what the non-trading-day
# fallback queries (`ctx.history.get_latest(src_key)`). The DSEX tile's
# fallback was pinned to the LEGACY `dse_dsex_close` series (frozen at 5,257 /
# 2026-04-21) while the chart already reads the LIVE `dsex` series — so on any
# stale day the tile showed a dead number under a live chart. Repointed to
# `dsex` (landmine #6; same live-vs-legacy split as landmine #1). The other
# six tiles had the same bug one level down: their fallback queried the
# `dse_`-prefixed display id, which EconDelta has never written to
# metric_history, so on non-trading days they resolved to None — the exact
# wall-of-None the fallback exists to prevent. Repointed to src_key for all
# seven rows. Landmine #17: a re-point only shows on prod after the next
# 06:30 BDT publish — verify PROD, not just preview.
_SPEC = (
    ("dsex",                 "DSEX close",       "dsex",              "index"),
    ("dse_dsex_change_pct",  "DSEX %Δ",          "dsex_change_pct",   "%"),
    ("dse_ds30",             "DS30",             "ds30",              "index"),
    ("dse_dses",             "DSES",             "dses",              "index"),
    ("dse_turnover_crore",   "Turnover",         "turnover_crore",    "crore BDT"),
    ("dse_advancing",        "Advancing",        "advancing",         "stocks"),
    ("dse_declining",        "Declining",        "declining",         "stocks"),
)

# Breadth data lives on the DSE homepage (div-based layout).
# The old endpoint /recent_market_information.php no longer contains this block.
_BREADTH_URL = "https://www.dsebd.org/"
# sector_indices.php returns HTTP 404 as of 2026-04.
# Kept for backward-compat parsing if the endpoint is restored.
_SECTOR_URL = "https://www.dsebd.org/sector_indices.php"
_SECTORS = ["Banks", "NBFI", "Textile", "Pharma", "Fuel", "Telecom", "Food", "IT"]

# Phase 3.1: per-sector keys EconDelta writes to Supabase metric_history.
# Order matches the V1 mockup's heatmap layout (4×2 grid, row-major).
_SECTOR_HEAT_KEYS: tuple[tuple[str, str], ...] = (
    ("Banks",   "dse_sector_heat_banks"),
    ("NBFI",    "dse_sector_heat_nbfi"),
    ("Textile", "dse_sector_heat_textile"),
    ("Pharma",  "dse_sector_heat_pharma"),
    ("Fuel",    "dse_sector_heat_fuel"),
    ("Telecom", "dse_sector_heat_telecom"),
    ("Food",    "dse_sector_heat_food"),
    ("IT",      "dse_sector_heat_it"),
)

# Browser-like User-Agent required; dsebd.org blocks plain urllib requests.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_REQUEST_TIMEOUT = 30  # seconds


@dataclass(frozen=True)
class BreadthResult:
    advancing: int
    declining: int
    unchanged: int
    as_of: datetime


@dataclass(frozen=True)
class SectorPerf:
    sector: str
    pct: float
    as_of: datetime


class _HomepageBreadthParser(HTMLParser):
    """Extract advancing/declining/unchanged counts from the DSE homepage.

    The DSE homepage encodes breadth data in a pair of sibling div rows:

        <div class="midrow mt10 mol_col-wid-cus">
          <div class="m_col-wid colorgreen">Issues Advanced</div>
          <div class="m_col-wid1 colorgreen">Issues declined</div>
          <div class="m_col-wid2 colorgreen">Issues Unchanged</div>
        </div>
        <div class="midrow mol_col-wid-cus" style="margin-top:1px;">
          <div class="m_col-wid colorlight">138</div>
          <div class="m_col-wid1 colorlight">199</div>
          <div class="m_col-wid2 colorlight">58</div>
        </div>

    Strategy:
      - Collect all texts from m_col-wid / m_col-wid1 / m_col-wid2 divs in order.
      - Scan the collected list for the pattern:
          ["Issues Advanced", "Issues declined", "Issues Unchanged", <int>, <int>, <int>]
      - Extract the three integers that follow the three label strings.
    """

    _DATA_CLASSES = {"m_col-wid", "m_col-wid1", "m_col-wid2"}

    def __init__(self) -> None:
        super().__init__()
        self._in_data_div = False
        self._current_text: list[str] = []
        self._collected: list[str] = []
        self._result: tuple[int, int, int] | None = None

    @staticmethod
    def _div_classes(attrs: list) -> set[str]:
        for name, value in attrs:
            if name == "class" and value:
                return set(value.split())
        return set()

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag != "div":
            return
        classes = self._div_classes(attrs)
        if classes & self._DATA_CLASSES:
            self._in_data_div = True
            self._current_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or not self._in_data_div:
            return
        self._in_data_div = False
        text = "".join(self._current_text).strip()
        self._collected.append(text)
        self._try_extract()

    def handle_data(self, data: str) -> None:
        if self._in_data_div:
            self._current_text.append(data)

    def _try_extract(self) -> None:
        """Scan collected texts for the breadth label+value pattern."""
        if self._result is not None:
            return
        items = self._collected
        # Look for the three label strings in sequence
        for i in range(len(items) - 5):
            if (
                "Issues Advanced" in items[i]
                and "Issues declined" in items[i + 1]
                and "Issues Unchanged" in items[i + 2]
            ):
                try:
                    a = int(items[i + 3])
                    d = int(items[i + 4])
                    u = int(items[i + 5])
                    self._result = (a, d, u)
                    return
                except (ValueError, IndexError):
                    pass

    @property
    def result(self) -> tuple[int, int, int] | None:
        return self._result


class _SectorParser(HTMLParser):
    """Extract sector name / pct pairs from a two-column table."""

    def __init__(self, target_sectors: list[str]) -> None:
        super().__init__()
        self._target = {s.lower(): s for s in target_sectors}
        self._in_td = False
        self._cells: list[str] = []
        self._row_cells: list[str] = []
        self.results: list[tuple[str, float]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "tr":
            self._row_cells = []
        elif tag == "td":
            self._in_td = True
            self._cells = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self._in_td = False
            self._row_cells.append("".join(self._cells).strip())
        elif tag == "tr":
            if len(self._row_cells) >= 2:
                name_raw = self._row_cells[0].strip()
                pct_raw = self._row_cells[1].strip()
                canonical = self._target.get(name_raw.lower())
                if canonical is not None:
                    try:
                        pct = float(pct_raw)
                        self.results.append((canonical, pct))
                    except ValueError:
                        pass

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cells.append(data)


def scrape_breadth(client: HttpClient | None = None) -> BreadthResult | None:
    """Scrape advancing/declining/unchanged counts from the DSE homepage.

    The breadth block lives at https://www.dsebd.org/ (homepage) in a pair of
    sibling div rows containing "Issues Advanced / Issues declined / Issues Unchanged"
    labels followed by integer values.

    Returns BreadthResult on success, None on any failure.
    """
    http = client if client is not None else UrllibHttp()
    headers = {"User-Agent": _BROWSER_UA}
    try:
        status, body = http.get(_BREADTH_URL, headers=headers)
        if status != 200:
            _log.warning("DSE breadth: HTTP %s", status)
            return None
        html = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        if not html:
            _log.warning("DSE breadth: empty response body")
            return None
        parser = _HomepageBreadthParser()
        parser.feed(html)
        if parser.result is None:
            _log.warning("DSE breadth: breadth block not found in homepage HTML")
            return None
        a, d, u = parser.result
        return BreadthResult(
            advancing=a,
            declining=d,
            unchanged=u,
            as_of=datetime.now(timezone.utc),
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("DSE breadth scrape failed: %s", exc)
        return None


def scrape_sector_heat(client: HttpClient | None = None) -> list[SectorPerf] | None:
    """Scrape sector performance percentages from DSE.

    NOTE: As of 2026-04, the endpoint https://www.dsebd.org/sector_indices.php
    returns HTTP 404.  This function returns None (graceful sentinel) in that
    case, which the builder treats as freshness="unavailable".  If the endpoint
    is restored the table-based parser below will handle it automatically.

    Returns list[SectorPerf] (possibly partial) on success, None on any failure
    or when the endpoint is unavailable.
    """
    http = client if client is not None else UrllibHttp()
    headers = {"User-Agent": _BROWSER_UA}
    try:
        status, body = http.get(_SECTOR_URL, headers=headers)
        if status != 200:
            _log.warning("DSE sector heat: HTTP %s (endpoint may be unavailable)", status)
            return None
        html = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        if not html:
            _log.warning("DSE sector heat: empty response body")
            return None
        parser = _SectorParser(_SECTORS)
        parser.feed(html)
        if not parser.results:
            _log.warning("DSE sector heat: no sector rows parsed from response")
            return None
        now = datetime.now(timezone.utc)
        # Preserve order from _SECTORS
        sector_map: dict[str, float] = {name: pct for name, pct in parser.results}
        ordered = [
            SectorPerf(sector=s, pct=sector_map[s], as_of=now)
            for s in _SECTORS
            if s in sector_map
        ]
        return ordered if ordered else None
    except Exception as exc:  # noqa: BLE001
        _log.warning("DSE sector heat scrape failed: %s", exc)
        return None


def _last_trading_day_before(today: date) -> date:
    """The most recent BD trading day strictly before `today`.

    The publish fires before the 10:00 BDT DSE open (AGENTS.md landmine on
    session-vs-run dating), so `today` itself is never a valid session date
    even when it is a trading day — the day's own session has not happened
    yet at publish time.
    """
    d = today - timedelta(days=1)
    while not is_bd_trading_day(d):
        d -= timedelta(days=1)
    return d


def _values_match(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return a == b


def _resolve_fresh_as_of(ctx: BuilderContext, src_key: str, value: Any) -> date:
    """Date a FRESH snapshot value by its trading SESSION, never by ctx.today.

    Issue 206 regression: EconDelta's snapshot dict (`brief/econdelta.py`) has
    no per-key session date, so dating every fresh value `as_of = ctx.today`
    dates the number by when the pipeline RAN, not by the session it actually
    describes. On 24 Aug the snapshot still held the 23 Aug close (DSE opens
    10:00 BDT; the brief fires ~08:16 BDT), so every DSE tile printed the
    label "24 Aug 2026" — a session that had not happened yet.

    Prefer the history row's `as_of` when its value matches the snapshot
    value (same confirmed session). If history is unreachable, has no row,
    or its value doesn't match (can't be trusted as the SAME session), fall
    back to the last BD trading day strictly before `ctx.today` — never the
    run date itself, but NOT an unconditionally safe upper bound: both paths
    are weekday-only (`is_bd_trading_day` has no BD public-holiday calendar,
    AGENTS.md landmine), so on a holiday the fallback can still name a day
    the market was closed, and a stale-but-coincidentally-equal history
    value can match the snapshot and hand back an older session's date.
    Strictly better than the `ctx.today` it replaces either way.
    """
    if ctx.history is not None:
        try:
            last = ctx.history.get_latest(src_key)
        except Exception:  # noqa: BLE001 — a history outage must not crash the builder
            _log.warning("DSE fresh as_of: get_latest(%s) failed, using trading-day fallback", src_key)
            last = None
        if last is not None:
            if _values_match(last.value, value):
                return last.as_of
            _log.debug(
                "DSE fresh as_of: get_latest(%s) value %r != snapshot value %r "
                "(history as_of=%s) — using trading-day fallback instead",
                src_key, last.value, value, last.as_of,
            )
    return _last_trading_day_before(ctx.today)


def build(ctx: BuilderContext) -> SectionData:
    # On non-trading days (Fri/Sat/holidays in BD), today's snapshot is empty.
    # Fall back to the last trading-day reading from Supabase metric_history,
    # so the section renders the last-known values with a "STALE" marker
    # rather than a wall of None. EconDelta upserts these keys daily.
    metrics: list[Metric] = []
    any_stale = False
    for (mid, label, src_key, unit) in _SPEC:
        value: Any = ctx.snapshot.get(src_key)
        is_stale = False
        if value is None:
            as_of = ctx.today
            if ctx.history is not None:
                last = ctx.history.get_latest(src_key)
                if last is not None:
                    value = last.value
                    as_of = last.as_of
                    is_stale = True
                    any_stale = True
        else:
            as_of = _resolve_fresh_as_of(ctx, src_key, value)
        metrics.append(Metric(
            id=mid, label=label, value=value, unit=unit,
            as_of=as_of, source="DSE",
            source_url="https://www.dse.com.bd/market-statistics.php",
            cadence="daily",
            stale=is_stale,
        ))

    section = SectionData(
        id="dse",
        title="DSE Markets",
        metrics=metrics,
        freshness="stale" if any_stale else section_freshness(metrics, today=ctx.today),
        freshness_reason=("Non-trading day — last trading session"
                          if any_stale else None),
    )

    # Breadth: prefer EconDelta's already-scraped advancing/declining/unchanged
    # (synced from BD-located ExonVPS via the rsync cron) over a duplicate
    # scrape from this VPS. The dsebd.org foreign-IP block makes the local
    # scrape fail from Hetzner anyway. Fall back only if EconDelta is empty.
    snap_adv = ctx.snapshot.get("advancing")
    snap_dec = ctx.snapshot.get("declining")
    snap_unc = ctx.snapshot.get("unchanged")
    if snap_adv is not None and snap_dec is not None:
        section.degraded_breadth = False
        if snap_unc is not None:
            section.extras["breadth_unchanged"] = snap_unc
    else:
        breadth = scrape_breadth()
        if breadth is None:
            section.degraded_breadth = True
        else:
            section.degraded_breadth = False
            section.extras["breadth_unchanged"] = breadth.unchanged

    # Sector heat (Phase 3.1): Option A — EconDelta computes from constituents
    # and writes 8 numeric keys to Supabase metric_history (one per sector).
    # We reconstruct the {sector: pct} dict here. Falls back to:
    #  (a) snapshot's dse_sector_heat dict if a local latest.json carries it,
    #  (b) the legacy DSE direct scrape (HTTP 404 since 2026-04).
    section.degraded_sector_heat = True
    sector_heat_rows: list[dict] = []
    if ctx.history is not None:
        for sector_label, key in _SECTOR_HEAT_KEYS:
            row = ctx.history.get_latest(key)
            if row is None or not isinstance(row.value, (int, float)):
                continue
            sector_heat_rows.append({
                "sector": sector_label,
                "pct": float(row.value),
                "as_of": row.as_of.isoformat(),
            })
    if sector_heat_rows:
        section.degraded_sector_heat = False
        section.extras["sector_heat"] = sector_heat_rows
    else:
        snap_heat = ctx.snapshot.get("dse_sector_heat")
        if isinstance(snap_heat, dict) and snap_heat:
            section.degraded_sector_heat = False
            section.extras["sector_heat"] = [
                {"sector": sec, "pct": pct, "as_of": ctx.today.isoformat()}
                for sec, pct in snap_heat.items()
                if isinstance(pct, (int, float))
            ]
        else:
            heat = scrape_sector_heat()
            if heat is not None:
                section.degraded_sector_heat = False
                section.extras["sector_heat"] = [
                    {"sector": sp.sector, "pct": sp.pct, "as_of": sp.as_of.isoformat()}
                    for sp in heat
                ]

    return section
