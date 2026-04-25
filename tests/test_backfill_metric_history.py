"""TDD tests for scripts/backfill_metric_history.py

Tests use injected mock HTTP clients — no live network calls.
Pattern mirrors tests/test_history.py: MagicMock injected via constructor.
"""
from __future__ import annotations

import sys
from datetime import date
from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Import guard — tests are written before the script exists (RED phase).
# ---------------------------------------------------------------------------
from scripts.backfill_metric_history import (
    BackfillClient,
    BackfillResult,
    build_dsex_rows,
    build_lng_rows,
    build_tbill_rows,
    build_yield_curve_rows,
    run_backfill,
)


# ---------------------------------------------------------------------------
# Fixtures — legacy table payloads (representative slices, not full prod data)
# ---------------------------------------------------------------------------

TB_DSEX_DAILY = [
    {"date": "2026-01-10", "close": 5234.56, "volume": 1000},
    {"date": "2026-01-11", "close": 5300.00, "volume": 1100},
    {"date": "2026-01-12", "close": 5280.50, "volume": 950},
]

TB_LNG_JKM_WEEKLY = [
    {"week_ending": "2026-01-05", "price_usd_mmbtu": 14.75, "source": "Platts"},
    {"week_ending": "2026-01-12", "price_usd_mmbtu": 15.10, "source": "Platts"},
]

TB_TBILL_AUCTIONS = [
    {"auction_date": "2026-01-08", "tenor_days": 91,  "yield_pct": 11.25, "issue": "T-Bill"},
    {"auction_date": "2026-01-08", "tenor_days": 182, "yield_pct": 11.50, "issue": "T-Bill"},
    {"auction_date": "2026-01-08", "tenor_days": 364, "yield_pct": 11.75, "issue": "T-Bill"},
    {"auction_date": "2026-01-15", "tenor_days": 91,  "yield_pct": 11.30, "issue": "T-Bill"},
    # A tenor not in the mapping (should be skipped)
    {"auction_date": "2026-01-15", "tenor_days": 28,  "yield_pct": 10.80, "issue": "T-Bill"},
]

TB_YIELD_CURVE = [
    {"as_of": "2026-01-10", "tenor": "5y",  "yield_pct": 11.80},
    {"as_of": "2026-01-10", "tenor": "10y", "yield_pct": 12.05},
    {"as_of": "2026-01-10", "tenor": "3m",  "yield_pct": 11.10},  # should be skipped
    {"as_of": "2026-01-10", "tenor": "2y",  "yield_pct": 11.50},  # should be skipped
    {"as_of": "2026-01-17", "tenor": "5y",  "yield_pct": 11.85},
    {"as_of": "2026-01-17", "tenor": "10y", "yield_pct": 12.10},
]

TB_BRENT_DAILY = [
    {"date": "2026-01-10", "price_usd_bbl": 82.50},
    {"date": "2026-01-11", "price_usd_bbl": 81.75},
]


# ---------------------------------------------------------------------------
# Unit tests: row-transformation functions (pure, no HTTP)
# ---------------------------------------------------------------------------

class TestBuildDsexRows:
    def test_maps_close_to_float_value(self):
        rows = build_dsex_rows(TB_DSEX_DAILY)
        assert len(rows) == 3
        first = rows[0]
        assert first.metric_id == "dse_dsex_close"
        assert first.as_of == date(2026, 1, 10)
        assert first.value == 5234.56
        assert isinstance(first.value, float)
        assert first.source == "DSE"

    def test_all_rows_have_correct_metric_id(self):
        rows = build_dsex_rows(TB_DSEX_DAILY)
        assert all(r.metric_id == "dse_dsex_close" for r in rows)

    def test_value_is_primitive_float_not_dict(self):
        """Builders read last.value directly as a number — must NOT be wrapped in dict."""
        rows = build_dsex_rows(TB_DSEX_DAILY)
        for row in rows:
            assert not isinstance(row.value, dict)
            assert isinstance(row.value, float)

    def test_empty_source_returns_empty(self):
        assert build_dsex_rows([]) == []


class TestBuildLngRows:
    def test_maps_price_usd_mmbtu_to_float_value(self):
        rows = build_lng_rows(TB_LNG_JKM_WEEKLY)
        assert len(rows) == 2
        assert rows[0].metric_id == "comm_lng_jkm"
        assert rows[0].as_of == date(2026, 1, 5)
        assert rows[0].value == 14.75
        assert isinstance(rows[0].value, float)
        assert rows[0].source == "Platts"

    def test_value_is_primitive_float_not_dict(self):
        rows = build_lng_rows(TB_LNG_JKM_WEEKLY)
        for row in rows:
            assert not isinstance(row.value, dict)
            assert isinstance(row.value, float)

    def test_empty_source_returns_empty(self):
        assert build_lng_rows([]) == []


class TestBuildTbillRows:
    def test_91d_maps_to_correct_metric_id(self):
        rows = build_tbill_rows(TB_TBILL_AUCTIONS)
        row_91 = next(r for r in rows if r.metric_id == "tbond_tbill_91d"
                      and r.as_of == date(2026, 1, 8))
        assert row_91.value == 11.25
        assert isinstance(row_91.value, float)
        assert row_91.source == "BB"

    def test_182d_maps_to_correct_metric_id(self):
        rows = build_tbill_rows(TB_TBILL_AUCTIONS)
        row_182 = next(r for r in rows if r.metric_id == "tbond_tbill_182d")
        assert row_182.value == 11.50
        assert row_182.metric_id == "tbond_tbill_182d"

    def test_364d_maps_to_correct_metric_id(self):
        rows = build_tbill_rows(TB_TBILL_AUCTIONS)
        row_364 = next(r for r in rows if r.metric_id == "tbond_tbill_364d")
        assert row_364.value == 11.75
        assert row_364.metric_id == "tbond_tbill_364d"

    def test_unknown_tenor_28d_is_skipped(self):
        rows = build_tbill_rows(TB_TBILL_AUCTIONS)
        metric_ids = [r.metric_id for r in rows]
        # tenor_days=28 has no mapping — must be absent
        for mid in metric_ids:
            assert "28" not in mid

    def test_row_count_excludes_unknown_tenors(self):
        # 3 known + 1 known on second date + 1 unknown skipped = 4 rows total
        rows = build_tbill_rows(TB_TBILL_AUCTIONS)
        assert len(rows) == 4

    def test_value_is_primitive_float_not_dict(self):
        rows = build_tbill_rows(TB_TBILL_AUCTIONS)
        for row in rows:
            assert not isinstance(row.value, dict)
            assert isinstance(row.value, float)

    def test_empty_source_returns_empty(self):
        assert build_tbill_rows([]) == []


class TestBuildYieldCurveRows:
    def test_5y_maps_to_tbond_bond_5y(self):
        rows = build_yield_curve_rows(TB_YIELD_CURVE)
        row_5y = next(r for r in rows if r.metric_id == "tbond_bond_5y"
                      and r.as_of == date(2026, 1, 10))
        assert row_5y.value == 11.80
        assert isinstance(row_5y.value, float)
        assert row_5y.source == "BB"

    def test_10y_maps_to_tbond_bond_10y(self):
        rows = build_yield_curve_rows(TB_YIELD_CURVE)
        row_10y = next(r for r in rows if r.metric_id == "tbond_bond_10y"
                       and r.as_of == date(2026, 1, 10))
        assert row_10y.value == 12.05

    def test_3m_tenor_is_skipped(self):
        rows = build_yield_curve_rows(TB_YIELD_CURVE)
        metric_ids = [r.metric_id for r in rows]
        assert "tbond_bond_3m" not in metric_ids
        # Double-check: no row with 3m tenor data (11.10)
        assert all(r.value != 11.10 for r in rows)

    def test_2y_tenor_is_skipped(self):
        rows = build_yield_curve_rows(TB_YIELD_CURVE)
        assert all(r.value != 11.50 for r in rows)

    def test_row_count_only_5y_and_10y(self):
        # 2 dates × 2 tenors (5y, 10y) = 4 rows; 3m and 2y skipped
        rows = build_yield_curve_rows(TB_YIELD_CURVE)
        assert len(rows) == 4

    def test_value_is_primitive_float_not_dict(self):
        rows = build_yield_curve_rows(TB_YIELD_CURVE)
        for row in rows:
            assert not isinstance(row.value, dict)
            assert isinstance(row.value, float)

    def test_empty_source_returns_empty(self):
        assert build_yield_curve_rows([]) == []


# ---------------------------------------------------------------------------
# Integration tests: BackfillClient (mocked HTTP)
# ---------------------------------------------------------------------------

def _make_mock_http(
    dsex_rows=None,
    lng_rows=None,
    tbill_rows=None,
    yield_rows=None,
    post_status=201,
):
    """Return a MagicMock HTTP client with canned GET/POST responses."""
    mock = MagicMock()
    dsex_rows = dsex_rows if dsex_rows is not None else TB_DSEX_DAILY
    lng_rows   = lng_rows   if lng_rows   is not None else TB_LNG_JKM_WEEKLY
    tbill_rows = tbill_rows if tbill_rows is not None else TB_TBILL_AUCTIONS
    yield_rows = yield_rows if yield_rows is not None else TB_YIELD_CURVE

    # GET responses: keyed by URL substring
    def _get(url, *, headers):
        if "tb_dsex_daily" in url:
            return (200, dsex_rows)
        if "tb_lng_jkm_weekly" in url:
            return (200, lng_rows)
        if "tb_tbill_auctions" in url:
            return (200, tbill_rows)
        if "tb_yield_curve" in url:
            return (200, yield_rows)
        if "tb_brent_daily" in url:
            return (200, TB_BRENT_DAILY)
        return (404, None)

    mock.get.side_effect = _get
    mock.post.return_value = (post_status, None)
    return mock


class TestBackfillClient:
    def test_fetch_dsex_returns_rows(self):
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        rows = client.fetch_source_rows("tb_dsex_daily", select="date,close")
        assert len(rows) == 3
        mock.get.assert_called_once()

    def test_brent_table_is_not_written_to_metric_history(self):
        """tb_brent_daily has no V4 hook — must never appear in POST payload."""
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        result = client.run(dry_run=False)
        # Collect all posted payloads
        posted_metric_ids = set()
        for c in mock.post.call_args_list:
            payload = c.kwargs.get("json") or []
            for item in payload:
                posted_metric_ids.add(item["metric_id"])
        assert "brent" not in " ".join(posted_metric_ids).lower()

    def test_upsert_uses_on_conflict_param_in_url(self):
        """PostgREST idempotency: ?on_conflict=metric_id,as_of must be in URL."""
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        client.run(dry_run=False)
        for post_call in mock.post.call_args_list:
            url = post_call.args[0] if post_call.args else post_call.kwargs.get("url", "")
            assert "on_conflict=metric_id%2Cas_of" in url or "on_conflict=metric_id,as_of" in url

    def test_upsert_uses_ignore_duplicates_prefer_header(self):
        """PostgREST: Prefer: resolution=ignore-duplicates for ON CONFLICT DO NOTHING."""
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        client.run(dry_run=False)
        for post_call in mock.post.call_args_list:
            headers = post_call.kwargs.get("headers", {})
            prefer = headers.get("Prefer", "")
            assert "ignore-duplicates" in prefer

    def test_run_returns_backfill_result_with_counts(self):
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        result = client.run(dry_run=False)
        assert isinstance(result, BackfillResult)
        # 3 dsex + 2 lng + 4 tbill(known tenors) + 4 yield(5y+10y only) = 13
        assert result.total_rows == 13

    def test_run_dry_run_does_not_call_post(self):
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        result = client.run(dry_run=True)
        mock.post.assert_not_called()
        assert result.total_rows == 13

    def test_run_dry_run_still_returns_correct_counts(self):
        mock = _make_mock_http()
        client = BackfillClient(
            url="https://example.supabase.co",
            service_key="svc",
            http=mock,
        )
        result = client.run(dry_run=True)
        assert result.dry_run is True
        assert result.total_rows == 13

    def test_idempotency_running_twice_posts_same_payload(self):
        """Running backfill twice produces identical POST payloads — server deduplicates."""
        mock1 = _make_mock_http()
        mock2 = _make_mock_http()
        client1 = BackfillClient(url="https://x.co", service_key="s", http=mock1)
        client2 = BackfillClient(url="https://x.co", service_key="s", http=mock2)
        client1.run(dry_run=False)
        client2.run(dry_run=False)
        calls1 = [c.kwargs.get("json") for c in mock1.post.call_args_list]
        calls2 = [c.kwargs.get("json") for c in mock2.post.call_args_list]
        assert calls1 == calls2

    def test_http_error_on_get_raises_or_returns_error_result(self):
        """A non-200 GET response should surface as an error, not silently drop rows."""
        mock = MagicMock()
        mock.get.return_value = (500, None)
        mock.post.return_value = (201, None)
        client = BackfillClient(url="https://x.co", service_key="s", http=mock)
        result = client.run(dry_run=False)
        assert result.errors > 0

    def test_post_failure_increments_error_count(self):
        mock = _make_mock_http(post_status=500)
        client = BackfillClient(url="https://x.co", service_key="s", http=mock)
        result = client.run(dry_run=False)
        assert result.errors > 0

    def test_all_metric_ids_in_posted_payload(self):
        """All five destination metric IDs must appear across POSTed rows."""
        mock = _make_mock_http()
        client = BackfillClient(url="https://x.co", service_key="s", http=mock)
        client.run(dry_run=False)
        posted_metric_ids = set()
        for c in mock.post.call_args_list:
            payload = c.kwargs.get("json") or []
            for item in payload:
                posted_metric_ids.add(item["metric_id"])
        expected = {
            "dse_dsex_close",
            "comm_lng_jkm",
            "tbond_tbill_91d",
            "tbond_tbill_182d",
            "tbond_tbill_364d",
            "tbond_bond_5y",
            "tbond_bond_10y",
        }
        assert expected.issubset(posted_metric_ids)

    def test_posted_values_are_primitives_not_dicts(self):
        """Builder consumers read .value directly — JSONB must be a primitive."""
        mock = _make_mock_http()
        client = BackfillClient(url="https://x.co", service_key="s", http=mock)
        client.run(dry_run=False)
        for c in mock.post.call_args_list:
            payload = c.kwargs.get("json") or []
            for item in payload:
                assert not isinstance(item["value"], dict), (
                    f"value for {item['metric_id']} must be a primitive, got dict"
                )

    def test_as_of_is_iso_date_string_in_payload(self):
        """PostgREST expects ISO date strings for the date column."""
        mock = _make_mock_http()
        client = BackfillClient(url="https://x.co", service_key="s", http=mock)
        client.run(dry_run=False)
        for c in mock.post.call_args_list:
            payload = c.kwargs.get("json") or []
            for item in payload:
                as_of = item["as_of"]
                # Must be parseable as ISO date
                parsed = date.fromisoformat(as_of)
                assert isinstance(parsed, date)


# ---------------------------------------------------------------------------
# CLI / run_backfill integration tests
# ---------------------------------------------------------------------------

class TestRunBackfill:
    def test_missing_supabase_url_raises_system_exit(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                run_backfill(dry_run=False)
        assert exc_info.value.code != 0

    def test_missing_service_key_raises_system_exit(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "https://x.co"}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                run_backfill(dry_run=False)
        assert exc_info.value.code != 0

    def test_successful_run_exits_0(self):
        mock = _make_mock_http()
        env = {
            "SUPABASE_URL": "https://x.co",
            "SUPABASE_SERVICE_KEY": "svc",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("scripts.backfill_metric_history.UrllibHttp", return_value=mock):
                result = run_backfill(dry_run=False)
        assert result == 0

    def test_error_run_exits_1(self):
        mock = _make_mock_http(post_status=500)
        env = {
            "SUPABASE_URL": "https://x.co",
            "SUPABASE_SERVICE_KEY": "svc",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("scripts.backfill_metric_history.UrllibHttp", return_value=mock):
                result = run_backfill(dry_run=False)
        assert result == 1

    def test_service_role_key_alias_accepted(self):
        """SUPABASE_SERVICE_ROLE_KEY is an accepted alias for SUPABASE_SERVICE_KEY."""
        mock = _make_mock_http()
        env = {
            "SUPABASE_URL": "https://x.co",
            "SUPABASE_SERVICE_ROLE_KEY": "svc-role",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("scripts.backfill_metric_history.UrllibHttp", return_value=mock):
                result = run_backfill(dry_run=False)
        assert result == 0

    def test_dry_run_flag_does_not_post(self):
        mock = _make_mock_http()
        env = {
            "SUPABASE_URL": "https://x.co",
            "SUPABASE_SERVICE_KEY": "svc",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("scripts.backfill_metric_history.UrllibHttp", return_value=mock):
                run_backfill(dry_run=True)
        mock.post.assert_not_called()
