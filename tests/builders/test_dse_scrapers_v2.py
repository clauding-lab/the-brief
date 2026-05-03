"""Tests for repaired DSE breadth + sector_heat scrapers (Issue #8).

Breadth endpoint changed from:
  dsebd.org/recent_market_information.php  (empty/non-JSON response)
to:
  dsebd.org/  (homepage, div-based breadth block)

Sector heat endpoint dsebd.org/sector_indices.php returns HTTP 404.
Scraper now returns None (graceful sentinel) with a warning log.
"""
from __future__ import annotations

import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brief.builders.dse import BreadthResult, SectorPerf, scrape_breadth, scrape_sector_heat

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"

_HOMEPAGE_BREADTH_HTML = (FIXTURES / "sample_dse_homepage_breadth.html").read_text()

_HOMEPAGE_BREADTH_HTML_BYTES = _HOMEPAGE_BREADTH_HTML.encode("utf-8")


def _make_client(status: int, body: str | bytes) -> MagicMock:
    """Return a mock HttpClient whose .get() returns (status, body)."""
    client = MagicMock()
    client.get.return_value = (status, body)
    return client


# ---------------------------------------------------------------------------
# Breadth: homepage div-based parser
# ---------------------------------------------------------------------------

class TestBreadthHomepageParser:
    """Tests for the new homepage div-layout breadth parser."""

    def test_homepage_html_parses_advancing(self):
        # Arrange
        client = _make_client(200, _HOMEPAGE_BREADTH_HTML)
        # Act
        result = scrape_breadth(client=client)
        # Assert
        assert result is not None
        assert result.advancing == 138

    def test_homepage_html_parses_declining(self):
        client = _make_client(200, _HOMEPAGE_BREADTH_HTML)
        result = scrape_breadth(client=client)
        assert result is not None
        assert result.declining == 199

    def test_homepage_html_parses_unchanged(self):
        client = _make_client(200, _HOMEPAGE_BREADTH_HTML)
        result = scrape_breadth(client=client)
        assert result is not None
        assert result.unchanged == 58

    def test_homepage_html_as_bytes_parses_correctly(self):
        # Arrange: server returns bytes (typical urllib response)
        client = _make_client(200, _HOMEPAGE_BREADTH_HTML_BYTES)
        # Act
        result = scrape_breadth(client=client)
        # Assert
        assert result is not None
        assert isinstance(result, BreadthResult)
        assert result.advancing == 138
        assert result.declining == 199
        assert result.unchanged == 58

    def test_homepage_html_result_is_breadth_result_dataclass(self):
        client = _make_client(200, _HOMEPAGE_BREADTH_HTML)
        result = scrape_breadth(client=client)
        assert isinstance(result, BreadthResult)

    def test_homepage_html_as_of_is_utc_aware_datetime(self):
        client = _make_client(200, _HOMEPAGE_BREADTH_HTML)
        result = scrape_breadth(client=client)
        assert result is not None
        assert isinstance(result.as_of, datetime)
        assert result.as_of.tzinfo is not None

    def test_homepage_html_missing_breadth_block_returns_none(self):
        # Arrange: page with no Issues Advanced/declined/Unchanged divs
        no_breadth_html = "<html><body><div>No market data here</div></body></html>"
        client = _make_client(200, no_breadth_html)
        # Act
        result = scrape_breadth(client=client)
        # Assert
        assert result is None

    def test_homepage_html_non_integer_values_returns_none(self):
        # Arrange: malformed breadth block with non-integer values
        bad_html = """
        <html><body>
        <div class="midrow mt10 mol_col-wid-cus">
          <div class="m_col-wid colorgreen">Issues Advanced</div>
          <div class="m_col-wid1 colorgreen">Issues declined</div>
          <div class="m_col-wid2 colorgreen">Issues Unchanged</div>
        </div>
        <div class="midrow mol_col-wid-cus">
          <div class="m_col-wid colorlight">N/A</div>
          <div class="m_col-wid1 colorlight">N/A</div>
          <div class="m_col-wid2 colorlight">N/A</div>
        </div>
        </body></html>
        """
        client = _make_client(200, bad_html)
        result = scrape_breadth(client=client)
        assert result is None


# ---------------------------------------------------------------------------
# Breadth: URL points to the homepage (not recent_market_information.php)
# ---------------------------------------------------------------------------

class TestBreadthUsesHomepageUrl:
    """The breadth scraper must request the DSE homepage, not the old URL."""

    def test_scraper_requests_homepage_url(self):
        # Arrange
        client = MagicMock()
        client.get.return_value = (200, _HOMEPAGE_BREADTH_HTML)
        # Act
        scrape_breadth(client=client)
        # Assert: the URL called must be the DSE homepage
        called_url = client.get.call_args[0][0]
        assert "dsebd.org" in called_url or "dse.com.bd" in called_url
        # Must NOT be the old broken endpoint
        assert "recent_market_information" not in called_url

    def test_scraper_sends_browser_user_agent(self):
        # Arrange
        client = MagicMock()
        client.get.return_value = (200, _HOMEPAGE_BREADTH_HTML)
        # Act
        scrape_breadth(client=client)
        # Assert: headers kwarg contains a User-Agent that looks like a browser
        call_kwargs = client.get.call_args[1]
        headers = call_kwargs.get("headers", {})
        ua = headers.get("User-Agent", "")
        assert "Mozilla" in ua, f"Expected browser UA, got: {ua!r}"


# ---------------------------------------------------------------------------
# Breadth: error paths (unchanged from before)
# ---------------------------------------------------------------------------

class TestBreadthErrorPaths:
    def test_non_200_returns_none(self):
        client = _make_client(404, b"Not Found")
        result = scrape_breadth(client=client)
        assert result is None

    def test_503_returns_none(self):
        client = _make_client(503, b"Service Unavailable")
        result = scrape_breadth(client=client)
        assert result is None

    def test_network_error_returns_none(self):
        client = MagicMock()
        client.get.side_effect = OSError("timed out")
        result = scrape_breadth(client=client)
        assert result is None

    def test_http_error_returns_none(self):
        client = MagicMock()
        client.get.side_effect = urllib.error.HTTPError(
            url="https://www.dsebd.org/",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        result = scrape_breadth(client=client)
        assert result is None

    def test_empty_body_returns_none(self):
        client = _make_client(200, "")
        result = scrape_breadth(client=client)
        assert result is None


# ---------------------------------------------------------------------------
# Sector heat: graceful sentinel on unavailable endpoint
# ---------------------------------------------------------------------------

class TestSectorHeatGracefulSentinel:
    """sector_indices.php returns 404; scraper should return None gracefully."""

    def test_404_response_returns_none(self):
        # Arrange: simulate the HTTP 404 the live endpoint now returns
        client = _make_client(404, b"Not Found")
        # Act
        result = scrape_sector_heat(client=client)
        # Assert: returns None (not an exception)
        assert result is None

    def test_empty_response_returns_none(self):
        client = _make_client(200, "")
        result = scrape_sector_heat(client=client)
        assert result is None

    def test_network_timeout_returns_none(self):
        client = MagicMock()
        client.get.side_effect = OSError("timed out")
        result = scrape_sector_heat(client=client)
        assert result is None

    def test_returns_none_type_not_exception(self):
        """Sentinel return must be None, not raise."""
        client = _make_client(404, b"")
        try:
            result = scrape_sector_heat(client=client)
            assert result is None
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"scrape_sector_heat raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Sector heat: still works when a valid table is provided (backward compat)
# ---------------------------------------------------------------------------

_VALID_SECTOR_HTML = """\
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
    <tr><td>Telecom</td><td>0.0</td></tr>
    <tr><td>Food</td><td>0.6</td></tr>
    <tr><td>IT</td><td>1.5</td></tr>
  </tbody>
</table>
</body></html>
"""


class TestSectorHeatBackwardCompat:
    """If a valid sector HTML is somehow available, parsing still works."""

    def test_valid_html_returns_sector_list(self):
        client = _make_client(200, _VALID_SECTOR_HTML)
        result = scrape_sector_heat(client=client)
        assert result is not None
        assert len(result) == 8

    def test_valid_html_returns_sector_perf_items(self):
        client = _make_client(200, _VALID_SECTOR_HTML)
        result = scrape_sector_heat(client=client)
        assert result is not None
        for item in result:
            assert isinstance(item, SectorPerf)

    def test_valid_html_values_correct(self):
        client = _make_client(200, _VALID_SECTOR_HTML)
        result = scrape_sector_heat(client=client)
        assert result is not None
        by_name = {sp.sector: sp.pct for sp in result}
        assert by_name["Banks"] == pytest.approx(1.2)
        assert by_name["IT"] == pytest.approx(1.5)
