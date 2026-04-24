"""Tests for DSE sector heat scraper (Task 2C.2)."""
from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brief.builders.dse import SectorPerf, scrape_sector_heat

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"

_FULL_SECTORS = ["Banks", "NBFI", "Textile", "Pharma", "Fuel", "Telecom", "Food", "IT"]

_PARTIAL_HTML = """\
<!DOCTYPE html>
<html><head><title>DSE Sector</title></head>
<body>
<table>
  <tbody>
    <tr><td>Banks</td><td>1.2</td></tr>
    <tr><td>NBFI</td><td>-0.5</td></tr>
    <tr><td>Textile</td><td>0.8</td></tr>
    <tr><td>Pharma</td><td>0.3</td></tr>
    <tr><td>Fuel</td><td>-1.1</td></tr>
  </tbody>
</table>
</body></html>
"""


def _make_client(status: int, body: str | bytes) -> MagicMock:
    client = MagicMock()
    client.get.return_value = (status, body)
    return client


def _full_html() -> str:
    return (FIXTURES / "sample_dse_sector_html.html").read_text()


class TestSectorHeatCannedHtml:
    def test_canned_html_yields_8_sectors(self):
        client = _make_client(200, _full_html())
        result = scrape_sector_heat(client=client)
        assert result is not None
        assert len(result) == 8
        names = [sp.sector for sp in result]
        assert names == _FULL_SECTORS

    def test_canned_html_values(self):
        client = _make_client(200, _full_html())
        result = scrape_sector_heat(client=client)
        assert result is not None
        by_name = {sp.sector: sp.pct for sp in result}
        assert by_name["Banks"] == pytest.approx(1.2)
        assert by_name["NBFI"] == pytest.approx(-0.5)
        assert by_name["Textile"] == pytest.approx(0.8)
        assert by_name["Fuel"] == pytest.approx(-1.1)
        assert by_name["Telecom"] == pytest.approx(0.0)
        assert by_name["IT"] == pytest.approx(1.5)

    def test_all_items_are_sector_perf(self):
        client = _make_client(200, _full_html())
        result = scrape_sector_heat(client=client)
        assert result is not None
        for item in result:
            assert isinstance(item, SectorPerf)
            assert item.as_of.tzinfo is not None


class TestSectorHeatPartialParse:
    def test_partial_parse_yields_partial_list(self):
        client = _make_client(200, _PARTIAL_HTML)
        result = scrape_sector_heat(client=client)
        assert result is not None
        assert len(result) == 5
        names = [sp.sector for sp in result]
        assert names == ["Banks", "NBFI", "Textile", "Pharma", "Fuel"]


class TestSectorHeatExceptionPaths:
    def test_exception_returns_none(self):
        client = MagicMock()
        client.get.side_effect = OSError("network failure")
        result = scrape_sector_heat(client=client)
        assert result is None

    def test_http_403_returns_none(self):
        client = MagicMock()
        client.get.side_effect = urllib.error.HTTPError(
            url="https://www.dsebd.org/sector_indices.php",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        result = scrape_sector_heat(client=client)
        assert result is None

    def test_non_200_status_returns_none(self):
        client = _make_client(503, b"")
        result = scrape_sector_heat(client=client)
        assert result is None
