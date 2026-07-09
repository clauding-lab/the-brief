"""Tests for brief/export.py — weekly off-box export (item 5e)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from brief.export import ExportError, TABLES, fetch_table, main, run_export


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")


class _FakeHttp:
    """Serves canned rows per table with real offset/limit pagination."""

    def __init__(self, rows_by_table: dict[str, list[dict]]):
        self.rows_by_table = rows_by_table
        self.requests: list[str] = []

    def get(self, url: str, *, headers: dict[str, str]):
        self.requests.append(url)
        parsed = urlparse(url)
        table = parsed.path.rsplit("/", 1)[-1]
        q = parse_qs(parsed.query)
        limit = int(q["limit"][0])
        offset = int(q["offset"][0])
        rows = self.rows_by_table.get(table, [])
        return 200, rows[offset : offset + limit]


def _rows(table: str, n: int) -> list[dict]:
    return [{"id": f"{table}-{i:05d}", "payload": f"row {i}"} for i in range(n)]


def test_fetch_table_paginates_past_page_size() -> None:
    http = _FakeHttp({"chart_series": _rows("chart_series", 2345)})
    out = fetch_table(
        http, supabase_url="https://test.supabase.co", service_key="k",
        table="chart_series",
    )
    assert len(out) == 2345
    assert out[0]["id"] == "chart_series-00000"
    assert out[-1]["id"] == "chart_series-02344"
    # 1000 + 1000 + 345 → 3 pages
    assert len(http.requests) == 3
    assert "offset=0" in http.requests[0]
    assert "offset=1000" in http.requests[1]
    assert "offset=2000" in http.requests[2]


def test_fetch_table_exact_page_boundary_stops() -> None:
    """Exactly page_size rows → a second (empty) page confirms completion."""
    http = _FakeHttp({"news": _rows("news", 1000)})
    out = fetch_table(
        http, supabase_url="https://test.supabase.co", service_key="k", table="news",
    )
    assert len(out) == 1000
    assert len(http.requests) == 2  # full page, then empty page


def test_fetch_table_raises_on_http_error() -> None:
    class _Failing:
        def get(self, url, *, headers):
            return 500, {"message": "boom"}

    with pytest.raises(ExportError, match="HTTP 500"):
        fetch_table(
            _Failing(), supabase_url="https://test.supabase.co", service_key="k",
            table="briefs",
        )


def test_run_export_writes_all_tables_and_manifest(tmp_path: Path) -> None:
    rows_by_table = {t: _rows(t, 3 + i) for i, t in enumerate(TABLES)}
    http = _FakeHttp(rows_by_table)

    dest = run_export(tmp_path, http=http, today=date(2026, 7, 9))

    assert dest == tmp_path / "2026-07-09"
    for i, t in enumerate(TABLES):
        data = json.loads((dest / f"{t}.json").read_text())
        assert len(data) == 3 + i
    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["export_date"] == "2026-07-09"
    assert manifest["tables"]["briefs"] == 3
    assert manifest["total_rows"] == sum(3 + i for i in range(len(TABLES)))


def test_run_export_refuses_empty_briefs(tmp_path: Path) -> None:
    """0 briefs rows = the export read nothing real — must FAIL (alert fires),
    not silently archive an empty dataset."""
    http = _FakeHttp({t: [] for t in TABLES})
    with pytest.raises(ExportError, match="0 briefs"):
        run_export(tmp_path, http=http, today=date(2026, 7, 9))


def test_run_export_prunes_beyond_keep(tmp_path: Path) -> None:
    # Pre-existing dated dirs + one non-dated dir that must survive
    for name in ("2026-01-03", "2026-01-10", "2026-01-17", "not-a-date"):
        (tmp_path / name).mkdir()
    http = _FakeHttp({t: _rows(t, 1) for t in TABLES})

    run_export(tmp_path, http=http, keep=2, today=date(2026, 7, 9))

    surviving = sorted(p.name for p in tmp_path.iterdir())
    # keep=2 → newest two dated dirs (2026-01-17, 2026-07-09) + the non-dated dir
    assert surviving == ["2026-01-17", "2026-07-09", "not-a-date"]


def test_main_returns_1_on_missing_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert main(["--out", str(tmp_path)]) == 1
