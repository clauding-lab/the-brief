"""Builder: DSE daily market snapshot."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from brief.cadence import section_freshness
from brief.history import HttpClient, UrllibHttp
from brief.schema import Metric, SectionData
from . import BuilderContext


_log = logging.getLogger(__name__)

_SPEC = (
    ("dse_dsex_close",       "DSEX close",       "dsex",              "index"),
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


def build(ctx: BuilderContext) -> SectionData:
    # On non-trading days (Fri/Sat/holidays in BD), today's snapshot is empty.
    # Fall back to the last trading-day reading from Supabase metric_history,
    # so the section renders the last-known values with a "STALE" marker
    # rather than a wall of None. EconDelta upserts these keys daily.
    metrics: list[Metric] = []
    any_stale = False
    for (mid, label, src_key, unit) in _SPEC:
        value: Any = ctx.snapshot.get(src_key)
        as_of = ctx.today
        is_stale = False
        if value is None and ctx.history is not None:
            last = ctx.history.get_latest(mid)
            if last is not None:
                value = last.value
                as_of = last.as_of
                is_stale = True
                any_stale = True
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

    # Sector heat: dsebd.org/sector_indices.php has returned HTTP 404 since
    # 2026-04 (data source dead). scrape_sector_heat() retained as a no-op
    # in case the endpoint is restored. degraded_sector_heat stays True
    # until either the endpoint comes back or a replacement source is wired.
    heat = scrape_sector_heat()
    if heat is None:
        section.degraded_sector_heat = True
    else:
        section.degraded_sector_heat = False
        section.extras["sector_heat"] = [
            {"sector": sp.sector, "pct": sp.pct, "as_of": sp.as_of.isoformat()}
            for sp in heat
        ]

    return section
