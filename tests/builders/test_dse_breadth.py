"""Tests for DSE breadth scraper (Task 2C.1)."""
from __future__ import annotations

import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brief.builders.dse import BreadthResult, scrape_breadth

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _make_client(status: int, body: str | bytes) -> MagicMock:
    """Return a mock HttpClient whose .get() returns (status, body)."""
    client = MagicMock()
    client.get.return_value = (status, body)
    return client


def _html() -> str:
    return (FIXTURES / "sample_dse_breadth_html.html").read_text()


class TestBreadthParsingCannedHtml:
    def test_canned_html_parses_correctly(self):
        client = _make_client(200, _html())
        result = scrape_breadth(client=client)
        assert result is not None
        assert isinstance(result, BreadthResult)
        assert result.advancing == 74
        assert result.declining == 162
        assert result.unchanged == 58
        assert isinstance(result.as_of, datetime)

    def test_as_of_is_utc_aware(self):
        client = _make_client(200, _html())
        result = scrape_breadth(client=client)
        assert result is not None
        assert result.as_of.tzinfo is not None


class TestBreadthExceptionPaths:
    def test_exception_path_returns_none(self):
        client = MagicMock()
        client.get.side_effect = OSError("network failure")
        result = scrape_breadth(client=client)
        assert result is None

    def test_http_403_returns_none(self):
        client = MagicMock()
        client.get.side_effect = urllib.error.HTTPError(
            url="https://www.dsebd.org/recent_market_information.php",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        result = scrape_breadth(client=client)
        assert result is None

    def test_non_200_status_returns_none(self):
        client = _make_client(503, b"Service Unavailable")
        result = scrape_breadth(client=client)
        assert result is None

    def test_empty_html_returns_none(self):
        client = _make_client(200, "<html><body></body></html>")
        result = scrape_breadth(client=client)
        assert result is None
