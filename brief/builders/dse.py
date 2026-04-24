"""Builder: DSE daily market snapshot."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser

from brief.cadence import section_freshness
from brief.history import HttpClient, UrllibHttp, HistoryRow
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

_BREADTH_URL = "https://www.dsebd.org/recent_market_information.php"
_SECTOR_URL = "https://www.dsebd.org/sector_indices.php"
_SECTORS = ["Banks", "NBFI", "Textile", "Pharma", "Fuel", "Telecom", "Food", "IT"]


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


class _BreadthParser(HTMLParser):
    """Extract the first table row with three integer cells."""

    def __init__(self) -> None:
        super().__init__()
        self._in_td = False
        self._cells: list[str] = []
        self._row_cells: list[str] = []
        self._result: tuple[int, int, int] | None = None

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
            if self._result is None and len(self._row_cells) >= 3:
                # Try parsing first three cells as integers
                try:
                    a = int(self._row_cells[0])
                    d = int(self._row_cells[1])
                    u = int(self._row_cells[2])
                    self._result = (a, d, u)
                except ValueError:
                    pass

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._cells.append(data)

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
    """Scrape advancing/declining/unchanged counts from DSE.

    Returns BreadthResult on success, None on any failure.
    """
    http = client if client is not None else UrllibHttp()
    try:
        status, body = http.get(_BREADTH_URL, headers={})
        if status != 200:
            _log.warning("DSE breadth: HTTP %s", status)
            return None
        html = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        parser = _BreadthParser()
        parser.feed(html)
        if parser.result is None:
            _log.warning("DSE breadth: no three-integer row found in HTML")
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

    Returns list of SectorPerf (possibly partial) on success, None on any failure.
    """
    http = client if client is not None else UrllibHttp()
    try:
        status, body = http.get(_SECTOR_URL, headers={})
        if status != 200:
            _log.warning("DSE sector heat: HTTP %s", status)
            return None
        html = body if isinstance(body, str) else body.decode("utf-8", errors="replace")
        parser = _SectorParser(_SECTORS)
        parser.feed(html)
        now = datetime.now(timezone.utc)
        # Preserve order from _SECTORS
        sector_map: dict[str, float] = {name: pct for name, pct in parser.results}
        ordered = [
            SectorPerf(sector=s, pct=sector_map[s], as_of=now)
            for s in _SECTORS
            if s in sector_map
        ]
        return ordered
    except Exception as exc:  # noqa: BLE001
        _log.warning("DSE sector heat scrape failed: %s", exc)
        return None


def build(ctx: BuilderContext) -> SectionData:
    metrics = [
        Metric(
            id=mid,
            label=label,
            value=ctx.snapshot.get(src_key),
            unit=unit,
            as_of=ctx.today,
            source="DSE",
            source_url="https://www.dse.com.bd/market-statistics.php",
            cadence="daily",
        )
        for (mid, label, src_key, unit) in _SPEC
    ]

    # Upsert DSEX close for history + downstream chart delta
    dsex = ctx.snapshot.get("dsex")
    if ctx.history is not None and dsex is not None:
        ctx.history.upsert_many([
            HistoryRow("dse_dsex_close", ctx.today, float(dsex), "DSE"),
        ])

    section = SectionData(
        id="dse",
        title="DSE Markets",
        metrics=metrics,
        freshness=section_freshness(metrics, today=ctx.today),
    )

    # Breadth scrape
    breadth = scrape_breadth()
    if breadth is None:
        section.degraded_breadth = True
    else:
        section.degraded_breadth = False

    # Sector heat scrape
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
