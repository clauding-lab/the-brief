"""Tests for deploy/heartbeat.py — the off-box fleet heartbeat (item 5b).

deploy/ is not a package; the module is loaded from its file path.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

_HB_PATH = Path(__file__).resolve().parent.parent / "deploy" / "heartbeat.py"
_spec = importlib.util.spec_from_file_location("heartbeat", _HB_PATH)
hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hb)


def _fetch_for(routes: dict[str, tuple[int, object]]):
    """Build a fetch(url, headers) stub routed by URL substring."""

    def _fetch(url: str, headers: dict[str, str]):
        for frag, resp in routes.items():
            if frag in url:
                return resp
        raise AssertionError(f"unexpected URL: {url}")

    return _fetch


# ── today_bdt: the timezone boundary ─────────────────────────────────────────


def test_today_bdt_is_next_day_before_6am_bdt() -> None:
    """THE trap: 23:30 UTC on Jul 9 is 05:30 BDT on Jul 10 — a UTC-computed
    'today' would be a day behind."""
    now = datetime(2026, 7, 9, 23, 30, tzinfo=timezone.utc)
    assert now.date() == date(2026, 7, 9)          # UTC says the 9th…
    assert hb.today_bdt(now) == date(2026, 7, 10)  # …but Bangladesh is on the 10th


def test_today_bdt_at_0730_bdt_run_time() -> None:
    """The scheduled 07:30 BDT run is 01:30 UTC of the SAME calendar day."""
    now = datetime(2026, 7, 10, 1, 30, tzinfo=timezone.utc)
    assert hb.today_bdt(now) == date(2026, 7, 10)


# ── check 1: The Brief published today ───────────────────────────────────────


def test_brief_published_today_is_healthy() -> None:
    fetch = _fetch_for({"/briefs": (200, [{"brief_date": "2026-07-10"}])})
    assert hb.check_brief_published_today(
        supabase_url="https://x", anon_key="k", today=date(2026, 7, 10), fetch=fetch,
    ) is None


def test_brief_stale_is_breach() -> None:
    fetch = _fetch_for({"/briefs": (200, [{"brief_date": "2026-07-08"}])})
    msg = hb.check_brief_published_today(
        supabase_url="https://x", anon_key="k", today=date(2026, 7, 10), fetch=fetch,
    )
    assert msg is not None and "2026-07-08" in msg and "2026-07-10" in msg


def test_brief_table_empty_is_breach() -> None:
    fetch = _fetch_for({"/briefs": (200, [])})
    msg = hb.check_brief_published_today(
        supabase_url="https://x", anon_key="k", today=date(2026, 7, 10), fetch=fetch,
    )
    assert msg is not None and "NO published briefs" in msg


def test_brief_check_at_tz_boundary_accepts_bdt_today() -> None:
    """At 05:30 BDT (23:30 UTC yesterday) with today's BDT brief already published,
    the check computed via today_bdt must be healthy — a UTC 'today' would breach."""
    now = datetime(2026, 7, 9, 23, 30, tzinfo=timezone.utc)
    fetch = _fetch_for({"/briefs": (200, [{"brief_date": "2026-07-10"}])})
    assert hb.check_brief_published_today(
        supabase_url="https://x", anon_key="k", today=hb.today_bdt(now), fetch=fetch,
    ) is None


def test_brief_query_filters_published_and_orders_desc() -> None:
    seen = {}

    def _fetch(url, headers):
        seen["url"] = url
        seen["headers"] = headers
        return 200, [{"brief_date": "2026-07-10"}]

    hb.check_brief_published_today(
        supabase_url="https://x", anon_key="anon-k", today=date(2026, 7, 10), fetch=_fetch,
    )
    assert "status=eq.published" in seen["url"]
    assert "order=brief_date.desc" in seen["url"]
    assert seen["headers"]["apikey"] == "anon-k"


# ── check 2: EconDelta freshness sentinel ────────────────────────────────────

_NOW = datetime(2026, 7, 10, 1, 30, tzinfo=timezone.utc)


def _sentinel_check(rows, now=_NOW, max_age=26.0):
    fetch = _fetch_for({"/run_logs": (200, rows)})
    return hb.check_sentinel_alive(
        supabase_url="https://x", anon_key="k", now_utc=now,
        max_age_hours=max_age, fetch=fetch,
    )


def test_sentinel_fresh_is_healthy() -> None:
    # Finished 12h ago (13:30 BDT yesterday = 07:30 UTC) — inside the 26h window
    assert _sentinel_check([{"finished_at": "2026-07-09T13:30:00+00:00"}]) is None


def test_sentinel_stale_is_breach() -> None:
    # Finished 30h ago — outside 26h
    msg = _sentinel_check([{"finished_at": "2026-07-08T19:30:00+00:00"}])
    assert msg is not None and "freshness_sentinel" in msg and "30.0h" in msg


def test_sentinel_absent_is_breach() -> None:
    msg = _sentinel_check([])
    assert msg is not None and "no ok freshness_sentinel row" in msg


def test_sentinel_z_suffix_timestamp_parses() -> None:
    assert _sentinel_check([{"finished_at": "2026-07-09T13:30:00Z"}]) is None


def test_sentinel_query_filters_ok_status() -> None:
    seen = {}

    def _fetch(url, headers):
        seen["url"] = url
        return 200, [{"finished_at": "2026-07-09T13:30:00Z"}]

    hb.check_sentinel_alive(
        supabase_url="https://x", anon_key="k", now_utc=_NOW, fetch=_fetch,
    )
    assert "source=eq.freshness_sentinel" in seen["url"]
    assert "status=eq.ok" in seen["url"]


# ── main: exit codes + alert wiring ──────────────────────────────────────────


@pytest.fixture()
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    monkeypatch.setenv("DISCORD_ALERT_WEBHOOK_URL", "https://discord.test/hook")


def test_main_exit_0_when_healthy(_env) -> None:
    healthy = _fetch_for({
        "/briefs": (200, [{"brief_date": hb.today_bdt().isoformat()}]),
        "/run_logs": (200, [{"finished_at": datetime.now(timezone.utc).isoformat()}]),
    })
    with patch.object(hb, "_fetch_json", healthy), \
         patch.object(hb, "send_discord_alert") as mock_alert:
        assert hb.main(["--env-file", "/nonexistent"]) == 0
    mock_alert.assert_not_called()


def test_main_exit_1_on_breach_with_alert(_env) -> None:
    breached = _fetch_for({
        "/briefs": (200, [{"brief_date": "2020-01-01"}]),
        "/run_logs": (200, []),
    })
    with patch.object(hb, "_fetch_json", breached), \
         patch.object(hb, "send_discord_alert", return_value=True) as mock_alert:
        assert hb.main(["--env-file", "/nonexistent"]) == 1
    mock_alert.assert_called_once()
    msg = mock_alert.call_args.args[1]
    assert "FLEET ALERT" in msg
    assert "2020-01-01" in msg                      # stale brief named
    assert "freshness_sentinel" in msg              # both breaches in ONE message


def test_main_exit_2_when_breach_alert_undeliverable(_env) -> None:
    breached = _fetch_for({
        "/briefs": (200, [{"brief_date": "2020-01-01"}]),
        "/run_logs": (200, []),
    })
    with patch.object(hb, "_fetch_json", breached), \
         patch.object(hb, "send_discord_alert", return_value=False):
        assert hb.main(["--env-file", "/nonexistent"]) == 2


def test_main_exit_2_when_supabase_unreachable(_env) -> None:
    def _down(url, headers):
        raise hb.HeartbeatError("connection refused")

    with patch.object(hb, "_fetch_json", _down), \
         patch.object(hb, "send_discord_alert", return_value=True) as mock_alert:
        assert hb.main(["--env-file", "/nonexistent"]) == 2
    # Best-effort self-report still attempted
    assert "HEARTBEAT FAILURE" in mock_alert.call_args.args[1]


def test_main_exit_2_on_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "DISCORD_ALERT_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)
    assert hb.main(["--env-file", "/nonexistent"]) == 2


# ── env file loading ─────────────────────────────────────────────────────────


def test_load_env_file_does_not_override_existing(tmp_path: Path) -> None:
    env_file = tmp_path / "hb.env"
    env_file.write_text(
        "# comment\n\nSUPABASE_URL=https://from-file\nDISCORD_ALERT_WEBHOOK_URL='https://hook'\n"
    )
    env: dict = {"SUPABASE_URL": "https://already-set"}
    hb.load_env_file(str(env_file), environ=env)
    assert env["SUPABASE_URL"] == "https://already-set"   # exported var wins
    assert env["DISCORD_ALERT_WEBHOOK_URL"] == "https://hook"  # quotes stripped


def test_load_env_file_missing_is_fine() -> None:
    hb.load_env_file("/definitely/not/a/file", environ={})
