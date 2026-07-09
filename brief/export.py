"""Weekly off-box export of `briefs` + all child tables (item 5e).

Supabase is the ONLY copy of every published issue, and the LLM-composed prose
(todays_call, verdicts, banker reads, analysis) is unreproducible — a lost table
is a lost archive. This module dumps the full editorial dataset to dated JSON
files so a copy exists off Supabase.

Usage (systemd runs this weekly via deploy/brief-export.timer):
  python -m brief.export --out /home/adnan/brief-exports [--keep 12]

Output layout:
  <out>/<YYYY-MM-DD>/briefs.json          (one JSON array per table)
  <out>/<YYYY-MM-DD>/sections.json
  <out>/<YYYY-MM-DD>/metrics.json
  <out>/<YYYY-MM-DD>/news.json
  <out>/<YYYY-MM-DD>/chart_series.json
  <out>/<YYYY-MM-DD>/chart_notes.json
  <out>/<YYYY-MM-DD>/manifest.json        ({exported_at, row counts per table})

Retention: keeps the newest `--keep` dated export dirs (default 12 ≈ 3 months of
weekly runs); older ones are deleted. Only dirs named exactly YYYY-MM-DD inside
the export root are ever touched.

Reads SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY) from the
environment — on Hetzner, /etc/brief.env via the unit's EnvironmentFile.

Exit codes: 0 ok · 1 export failed (systemd OnFailure= fires the Discord alert).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import urllib.parse
from datetime import date as date_t
from datetime import datetime, timezone
from pathlib import Path

from brief.history import HttpClient, UrllibHttp

logger = logging.getLogger(__name__)

# Every table that carries a piece of a published issue. `briefs` is the parent;
# the rest cascade from it (see v6_publisher). All have an `id` column (verified
# against production information_schema, 2026-07-09).
TABLES: tuple[str, ...] = (
    "briefs",
    "sections",
    "metrics",
    "news",
    "chart_series",
    "chart_notes",
)

# PostgREST caps result sets (default max-rows 1000); page deterministically.
PAGE_SIZE: int = 1000

_DATED_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ExportError(RuntimeError):
    """Raised when any table fetch or file write fails — the export must be
    all-or-nothing per run so a manifest never lies about what's on disk."""


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise ExportError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY env vars. "
            "On Hetzner these come from /etc/brief.env via systemd EnvironmentFile."
        )
    return url.rstrip("/"), key


def fetch_table(
    http: HttpClient,
    *,
    supabase_url: str,
    service_key: str,
    table: str,
    page_size: int = PAGE_SIZE,
) -> list[dict]:
    """Fetch EVERY row of `table` via deterministic offset pagination.

    Ordered by `id.asc` so pages are stable across the run. Raises ExportError
    on any non-200 or non-list page — a partial table must never be written as
    if complete.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        q = urllib.parse.urlencode(
            {
                "select": "*",
                "order": "id.asc",
                "limit": str(page_size),
                "offset": str(offset),
            }
        )
        url = f"{supabase_url}/rest/v1/{table}?{q}"
        status, body = http.get(
            url,
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
        )
        if status != 200 or not isinstance(body, list):
            raise ExportError(
                f"fetch {table} page offset={offset} failed: HTTP {status} "
                f"(body type {type(body).__name__})"
            )
        rows.extend(body)
        if len(body) < page_size:
            return rows
        offset += page_size


def _prune_old_exports(out_root: Path, keep: int) -> list[str]:
    """Delete the oldest dated export dirs beyond `keep`. Returns deleted names.

    Only touches direct children of `out_root` whose name is exactly YYYY-MM-DD —
    anything else in the directory is left alone.
    """
    dated = sorted(
        d for d in out_root.iterdir() if d.is_dir() and _DATED_DIR_RE.match(d.name)
    )
    doomed = dated[:-keep] if keep > 0 else []
    deleted: list[str] = []
    for d in doomed:
        shutil.rmtree(d)
        deleted.append(d.name)
        logger.info("export: pruned old export %s", d.name)
    return deleted


def run_export(
    out_root: str | Path,
    *,
    http: HttpClient | None = None,
    keep: int = 12,
    today: date_t | None = None,
) -> Path:
    """Export all TABLES to `<out_root>/<today>/`, write a manifest, prune old runs.

    Returns the dated export directory. Raises ExportError on any failure.
    """
    supabase_url, service_key = _config()
    http = http if http is not None else UrllibHttp()
    today = today or datetime.now(timezone.utc).date()

    out_root = Path(out_root)
    dest = out_root / today.isoformat()
    dest.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for table in TABLES:
        rows = fetch_table(
            http, supabase_url=supabase_url, service_key=service_key, table=table
        )
        path = dest / f"{table}.json"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
        except OSError as e:
            raise ExportError(f"write {path} failed: {e}") from e
        counts[table] = len(rows)
        logger.info("export: %s → %d rows", table, len(rows))

    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "export_date": today.isoformat(),
        "tables": counts,
        "total_rows": sum(counts.values()),
    }
    with open(dest / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    if counts.get("briefs", 0) == 0:
        # Zero briefs means the export read NOTHING real — treat as failure so the
        # OnFailure alert fires rather than silently archiving an empty dataset.
        raise ExportError("export fetched 0 briefs rows — refusing to call this a backup")

    _prune_old_exports(out_root, keep)
    logger.info(
        "export: done — %d tables, %d total rows → %s", len(counts),
        manifest["total_rows"], dest,
    )
    return dest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    p = argparse.ArgumentParser(
        prog="brief.export", description="Export briefs + child tables to dated JSON"
    )
    p.add_argument(
        "--out",
        default=os.environ.get("BRIEF_EXPORT_DIR", "exports"),
        help="Export root directory (default: $BRIEF_EXPORT_DIR or ./exports)",
    )
    p.add_argument(
        "--keep", type=int, default=12,
        help="How many dated exports to retain (default 12 ≈ 3 months weekly)",
    )
    ns = p.parse_args(argv)

    try:
        dest = run_export(ns.out, keep=ns.keep)
    except ExportError as e:
        logger.error("export failed: %s", e)
        return 1
    except Exception:
        logger.exception("export failed unexpectedly")
        return 1

    print(dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
