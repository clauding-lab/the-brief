"""Builder tests never reach dsebd.org.

brief.builders.dse falls back to a direct dsebd.org scrape (sector heat, and breadth when the
snapshot lacks it) through its default HTTP client. In tests that default client is replaced by
one that behaves like production on Hetzner, where dsebd.org blocks the foreign IP: every
request fails, so the scrapers return their "unavailable" sentinel (None). Scraper unit tests
that pass their own fake client are unaffected.
"""
from __future__ import annotations

from typing import Any

import pytest

from brief.builders import dse


class _UnreachableDseHttp:
    """Default DSE client for tests: dsebd.org is unreachable, as it is from the Hetzner box."""

    def get(self, url: str, *, headers: dict[str, str]) -> tuple[int, Any]:
        raise ConnectionError(f"dsebd.org is not reachable from tests: GET {url}")

    def post(self, url: str, *, headers: dict[str, str], json: Any) -> tuple[int, Any]:
        raise ConnectionError(f"dsebd.org is not reachable from tests: POST {url}")


@pytest.fixture(autouse=True)
def _dse_scrapes_are_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dse, "UrllibHttp", _UnreachableDseHttp)
