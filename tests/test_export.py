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
    """Serves canned rows per table with real KEYSET pagination semantics
    (`id=gt.<last>` + `order=id.asc` + `limit`), like PostgREST would.

    `fail_table` forces a 500 on that table (partial-failure paths).
    `after_first_page` is an optional callback run once after the first page of
    any table is served — used to mutate the backing store mid-pagination and
    prove keyset immunity to the publish-window race.
    """

    def __init__(self, rows_by_table, *, fail_table=None, after_first_page=None):
        self.rows_by_table = rows_by_table
        self.fail_table = fail_table
        self.after_first_page = after_first_page
        self.requests: list[str] = []
        self._pages_served = 0

    def get(self, url: str, *, headers: dict[str, str]):
        self.requests.append(url)
        parsed = urlparse(url)
        table = parsed.path.rsplit("/", 1)[-1]
        if table == self.fail_table:
            return 500, {"message": "boom"}
        q = parse_qs(parsed.query)
        limit = int(q["limit"][0])
        rows = sorted(self.rows_by_table.get(table, []), key=lambda r: r["id"])
        id_filter = q.get("id", [None])[0]
        if id_filter and id_filter.startswith("gt."):
            last = id_filter[3:]
            rows = [r for r in rows if r["id"] > last]
        page = rows[:limit]
        self._pages_served += 1
        if self._pages_served == 1 and self.after_first_page is not None:
            self.after_first_page(self)
        return 200, page


def _rows(table: str, n: int) -> list[dict]:
    return [{"id": f"{table}-{i:05d}", "payload": f"row {i}"} for i in range(n)]


# ── fetch_table: keyset pagination ────────────────────────────────────────────


def test_fetch_table_paginates_past_page_size() -> None:
    http = _FakeHttp({"chart_series": _rows("chart_series", 2345)})
    out = fetch_table(
        http, supabase_url="https://test.supabase.co", service_key="k",
        table="chart_series",
    )
    assert len(out) == 2345
    assert out[0]["id"] == "chart_series-00000"
    assert out[-1]["id"] == "chart_series-02344"
    # 1000 + 1000 + 345 → 3 pages; pages 2 and 3 are keyset (id=gt.<last>), not offset
    assert len(http.requests) == 3
    assert "id=" not in http.requests[0]
    assert "id=gt.chart_series-00999" in http.requests[1]
    assert "id=gt.chart_series-01999" in http.requests[2]
    assert "offset" not in http.requests[1]


def test_fetch_table_exact_page_boundary_stops() -> None:
    """Exactly page_size rows → a second (empty) keyset page confirms completion."""
    http = _FakeHttp({"news": _rows("news", 1000)})
    out = fetch_table(
        http, supabase_url="https://test.supabase.co", service_key="k", table="news",
    )
    assert len(out) == 1000
    assert len(http.requests) == 2  # full page, then empty page
    assert "id=gt.news-00999" in http.requests[1]


def test_fetch_table_keyset_immune_to_mid_export_delete() -> None:
    """The publish-window race (review MEDIUM): the publisher's DELETE between
    paged GETs shifts offsets and makes OFFSET pagination skip rows. Keyset must
    visit every SURVIVING row exactly once regardless."""
    rows = _rows("sections", 1500)

    def _delete_some(fake: _FakeHttp) -> None:
        # After page 1 (ids 00000-00999) is served, the publisher deletes 100
        # already-seen rows — under offset pagination the next page would skip
        # 100 unseen rows; keyset must not.
        fake.rows_by_table["sections"] = [
            r for r in fake.rows_by_table["sections"]
            if not ("sections-00100" <= r["id"] <= "sections-00199")
        ]

    http = _FakeHttp({"sections": rows}, after_first_page=_delete_some)
    out = fetch_table(
        http, supabase_url="https://test.supabase.co", service_key="k",
        table="sections",
    )
    # All 1500 ids collected: 1000 seen before the delete + the 500 after it —
    # nothing skipped, nothing double-counted.
    ids = [r["id"] for r in out]
    assert len(ids) == 1500
    assert len(set(ids)) == 1500
    assert "sections-01000" in ids and "sections-01499" in ids  # the at-risk rows


def test_fetch_table_raises_on_http_error() -> None:
    http = _FakeHttp({}, fail_table="briefs")
    with pytest.raises(ExportError, match="HTTP 500"):
        fetch_table(
            http, supabase_url="https://test.supabase.co", service_key="k",
            table="briefs",
        )


def test_fetch_table_raises_on_row_missing_id() -> None:
    """A full page whose last row lacks `id` makes keyset continuation impossible —
    fetch_table must fail loudly rather than silently stop early."""

    class _NoIdFake:
        def get(self, url, *, headers):
            return 200, [{"payload": f"row {i}"} for i in range(1000)]  # full page, no ids

    with pytest.raises(ExportError, match="missing 'id'"):
        fetch_table(
            _NoIdFake(), supabase_url="https://test.supabase.co", service_key="k",
            table="briefs",
        )


# ── run_export: staging + atomic promote ─────────────────────────────────────


def _no_dated_dirs(root: Path) -> bool:
    import re
    return not any(
        p.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", p.name) for p in root.iterdir()
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
    # No staging leftovers after a successful promote
    assert not list(tmp_path.glob(".staging-*"))


def test_run_export_midloop_failure_leaves_nothing_dated(tmp_path: Path) -> None:
    """Forced-failure path 1 (review MEDIUM): a fetch failure on table 3 must leave
    NO dated dir and NO staging leftovers — never a partial 2-of-6 export."""
    rows_by_table = {t: _rows(t, 2) for t in TABLES}
    http = _FakeHttp(rows_by_table, fail_table="metrics")  # 3rd table

    with pytest.raises(ExportError, match="HTTP 500"):
        run_export(tmp_path, http=http, today=date(2026, 7, 9))

    assert _no_dated_dirs(tmp_path), "partial export must not be promoted to a dated dir"
    assert not list(tmp_path.glob(".staging-*")), "failed staging dir must be cleaned"


def test_run_export_zero_briefs_leaves_nothing_dated(tmp_path: Path) -> None:
    """Forced-failure path 2 (review MEDIUM): the refuse-0-briefs guard must fire
    BEFORE anything is promoted — no phantom fully-formed empty backup may occupy
    a retention slot."""
    http = _FakeHttp({t: [] for t in TABLES})

    with pytest.raises(ExportError, match="0 briefs"):
        run_export(tmp_path, http=http, today=date(2026, 7, 9))

    assert _no_dated_dirs(tmp_path)
    assert not list(tmp_path.glob(".staging-*"))
    # And absolutely no manifest anywhere — the phantom-backup artifact
    assert not list(tmp_path.rglob("manifest.json"))


def test_run_export_cleans_stale_staging_from_crashed_run(tmp_path: Path) -> None:
    """A SIGKILLed previous run leaves a .staging-* dir; the next run removes it."""
    stale = tmp_path / ".staging-dead"
    stale.mkdir()
    (stale / "briefs.json").write_text("[]")
    http = _FakeHttp({t: _rows(t, 1) for t in TABLES})

    run_export(tmp_path, http=http, today=date(2026, 7, 9))

    assert not stale.exists()
    assert (tmp_path / "2026-07-09" / "manifest.json").exists()


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
