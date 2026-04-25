"""Backfill script: populate metric_history from legacy tb_* tables.

Usage:
    python scripts/backfill_metric_history.py [--dry-run]

Required environment variables:
    SUPABASE_URL         - e.g. https://abcdef.supabase.co
    SUPABASE_SERVICE_KEY - service role key (also accepted as SUPABASE_SERVICE_ROLE_KEY)

Idempotent: uses ON CONFLICT (metric_id, as_of) DO NOTHING via PostgREST
    Prefer: resolution=ignore-duplicates

Source → Destination mapping:
    tb_dsex_daily      → dse_dsex_close       (value = float(close))
    tb_lng_jkm_weekly  → comm_lng_jkm         (value = float(price_usd_mmbtu))
    tb_tbill_auctions  → tbond_tbill_91d /
                         tbond_tbill_182d /
                         tbond_tbill_364d     (split by tenor_days; value = float(yield_pct))
    tb_yield_curve     → tbond_bond_5y /
                         tbond_bond_10y       (filter tenor IN ('5y','10y'); value = float(yield_pct))
    tb_brent_daily     → SKIP (no V4 consumer)

DO NOT run against production without explicit authorization.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from brief.history import HistoryRow, HttpClient, MetricHistoryClient, UrllibHttp

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tenor mappings
# ---------------------------------------------------------------------------

_TBILL_TENOR_MAP: dict[int, str] = {
    91:  "tbond_tbill_91d",
    182: "tbond_tbill_182d",
    364: "tbond_tbill_364d",
}

_YIELD_TENOR_MAP: dict[str, str] = {
    "5y":  "tbond_bond_5y",
    "10y": "tbond_bond_10y",
}


# ---------------------------------------------------------------------------
# Pure row-transformation functions (no I/O)
# ---------------------------------------------------------------------------

def build_dsex_rows(source_rows: list[dict]) -> list[HistoryRow]:
    """Transform tb_dsex_daily rows → HistoryRow(dse_dsex_close, ...)."""
    result = []
    for row in source_rows:
        result.append(HistoryRow(
            metric_id="dse_dsex_close",
            as_of=date.fromisoformat(row["date"]),
            value=float(row["close"]),
            source="DSE",
        ))
    return result


def build_lng_rows(source_rows: list[dict]) -> list[HistoryRow]:
    """Transform tb_lng_jkm_weekly rows → HistoryRow(comm_lng_jkm, ...)."""
    result = []
    for row in source_rows:
        result.append(HistoryRow(
            metric_id="comm_lng_jkm",
            as_of=date.fromisoformat(row["week_ending"]),
            value=float(row["price_usd_mmbtu"]),
            source="Platts",
        ))
    return result


def build_tbill_rows(source_rows: list[dict]) -> list[HistoryRow]:
    """Transform tb_tbill_auctions rows → HistoryRow per known tenor.

    Rows with tenor_days not in {91, 182, 364} are silently skipped.
    """
    result = []
    for row in source_rows:
        tenor = int(row["tenor_days"])
        metric_id = _TBILL_TENOR_MAP.get(tenor)
        if metric_id is None:
            _log.debug("Skipping tbill auction tenor_days=%s (no V4 metric)", tenor)
            continue
        result.append(HistoryRow(
            metric_id=metric_id,
            as_of=date.fromisoformat(row["auction_date"]),
            value=float(row["yield_pct"]),
            source="BB",
        ))
    return result


def build_yield_curve_rows(source_rows: list[dict]) -> list[HistoryRow]:
    """Transform tb_yield_curve rows → HistoryRow for 5y and 10y only.

    Rows with tenor not in ('5y', '10y') are silently skipped.
    """
    result = []
    for row in source_rows:
        tenor = row["tenor"]
        metric_id = _YIELD_TENOR_MAP.get(tenor)
        if metric_id is None:
            _log.debug("Skipping yield_curve tenor=%s (no V4 metric)", tenor)
            continue
        result.append(HistoryRow(
            metric_id=metric_id,
            as_of=date.fromisoformat(row["as_of"]),
            value=float(row["yield_pct"]),
            source="BB",
        ))
    return result


# ---------------------------------------------------------------------------
# BackfillResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class BackfillResult:
    total_rows: int = 0
    errors: int = 0
    dry_run: bool = False


# ---------------------------------------------------------------------------
# BackfillClient — wraps HTTP seam, mirrors MetricHistoryClient pattern
# ---------------------------------------------------------------------------

class BackfillClient:
    """Reads legacy tb_* tables and writes to metric_history.

    Injects an HttpClient for testing; production passes UrllibHttp (default).
    """

    def __init__(self, *, url: str, service_key: str, http: HttpClient | None = None):
        self.url = url.rstrip("/")
        self.key = service_key
        self.http = http or UrllibHttp()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def fetch_source_rows(self, table: str, select: str) -> list[dict]:
        """GET all rows from a PostgREST table with the given select projection."""
        params = urllib.parse.urlencode({"select": select})
        url = f"{self.url}/rest/v1/{table}?{params}"
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or body is None:
            raise RuntimeError(f"GET {table} returned HTTP {status}")
        return body

    def _upsert_rows(self, rows: list[HistoryRow]) -> None:
        """POST rows to metric_history with ignore-duplicates conflict resolution."""
        if not rows:
            return
        url = (
            f"{self.url}/rest/v1/metric_history"
            f"?on_conflict=metric_id,as_of"
        )
        payload = [
            {
                "metric_id": r.metric_id,
                "as_of": r.as_of.isoformat(),
                "value": r.value,
                "source": r.source,
            }
            for r in rows
        ]
        status, _ = self.http.post(
            url,
            headers=self._headers({
                "Prefer": "resolution=ignore-duplicates,return=minimal",
            }),
            json=payload,
        )
        if status not in (200, 201, 204):
            raise RuntimeError(f"POST metric_history returned HTTP {status}")

    def run(self, *, dry_run: bool = False) -> BackfillResult:
        """Execute the full backfill across all source tables.

        Returns a BackfillResult with counts. Does not POST if dry_run=True.
        """
        result = BackfillResult(dry_run=dry_run)

        sources: list[tuple[str, str, Any]] = [
            ("tb_dsex_daily",     "date,close",                         build_dsex_rows),
            ("tb_lng_jkm_weekly", "week_ending,price_usd_mmbtu,source", build_lng_rows),
            ("tb_tbill_auctions", "auction_date,tenor_days,yield_pct",  build_tbill_rows),
            ("tb_yield_curve",    "as_of,tenor,yield_pct",              build_yield_curve_rows),
            # tb_brent_daily intentionally omitted — no V4 consumer
        ]

        all_rows: list[HistoryRow] = []

        for table, select, transform in sources:
            try:
                raw = self.fetch_source_rows(table, select)
            except RuntimeError as exc:
                _log.error("Failed to fetch %s: %s", table, exc)
                result.errors += 1
                continue

            rows = transform(raw)
            _log.info("  %s → %d rows", table, len(rows))
            all_rows.extend(rows)

        result.total_rows = len(all_rows)

        if dry_run:
            _log.info("[dry-run] Would insert %d rows into metric_history", result.total_rows)
            for row in all_rows:
                _log.info("  [dry-run] %s | %s | %r | %s",
                          row.metric_id, row.as_of, row.value, row.source)
            return result

        # POST in a single batch (idempotent via ignore-duplicates)
        if all_rows:
            try:
                self._upsert_rows(all_rows)
                _log.info("Inserted/skipped %d rows into metric_history", result.total_rows)
            except RuntimeError as exc:
                _log.error("POST metric_history failed: %s", exc)
                result.errors += 1

        return result


# ---------------------------------------------------------------------------
# run_backfill — entry point used by CLI and tests
# ---------------------------------------------------------------------------

def run_backfill(*, dry_run: bool = False) -> int:
    """Read env vars, build client, run backfill. Returns exit code (0 or 1)."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY", "")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()

    if not url:
        print("ERROR: SUPABASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)
    if not key:
        print(
            "ERROR: SUPABASE_SERVICE_KEY (or SUPABASE_SERVICE_ROLE_KEY) "
            "environment variable is required",
            file=sys.stderr,
        )
        sys.exit(1)

    client = BackfillClient(url=url, service_key=key)
    result = client.run(dry_run=dry_run)

    if result.errors > 0:
        _log.error("Backfill completed with %d error(s)", result.errors)
        return 1

    _log.info(
        "Backfill complete. total_rows=%d dry_run=%s errors=%d",
        result.total_rows, result.dry_run, result.errors,
    )
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Backfill metric_history from legacy tb_* tables"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print would-be rows without writing to Supabase",
    )
    args = parser.parse_args()
    sys.exit(run_backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    _main()
