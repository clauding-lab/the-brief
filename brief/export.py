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
import tempfile
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
    """Fetch EVERY row of `table` via KEYSET pagination (`id=gt.<last>` + `order=id.asc`).

    Keyset, not offset (review MEDIUM): the Saturday publish can run until ~08:00 BDT
    under the documented 529-retry worst case, and the publisher's DELETE/re-INSERT
    (two-phase publish) between paged GETs shifts offsets — offset pagination then
    silently skips rows. Keyset asks each page for ids strictly greater than the last
    id seen, so concurrent deletes/inserts cannot renumber what remains; every
    surviving row is visited exactly once.

    Raises ExportError on any non-200/non-list page or a row missing `id` — a partial
    table must never be treated as complete.
    """
    rows: list[dict] = []
    last_id: str | None = None
    while True:
        params: list[tuple[str, str]] = [
            ("select", "*"),
            ("order", "id.asc"),
            ("limit", str(page_size)),
        ]
        if last_id is not None:
            params.append(("id", f"gt.{last_id}"))
        q = urllib.parse.urlencode(params)
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
                f"fetch {table} page after id={last_id!r} failed: HTTP {status} "
                f"(body type {type(body).__name__})"
            )
        rows.extend(body)
        if len(body) < page_size:
            return rows
        last = body[-1].get("id")
        if last is None:
            raise ExportError(
                f"{table} row missing 'id' — keyset pagination impossible"
            )
        last_id = str(last)


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

    All-or-nothing is ENFORCED via a staging dir (review MEDIUM — the same idiom as
    the publisher's draft→published flip): every table + the manifest is written to
    a `.staging-*` dir (whose name never matches the dated regex, so pruning ignores
    it), ALL guards run (including refuse-0-briefs), and only on full success is the
    staging dir atomically renamed to `<YYYY-MM-DD>`. A mid-loop failure therefore
    leaves NO partial dated dir, and a phantom empty backup can never occupy a
    retention slot. On any failure the staging dir is removed before re-raising.

    Returns the dated export directory. Raises ExportError on any failure.
    """
    supabase_url, service_key = _config()
    http = http if http is not None else UrllibHttp()
    today = today or datetime.now(timezone.utc).date()

    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    dest = out_root / today.isoformat()

    # Clear leftover staging dirs from crashed runs (SIGKILL etc.) — by definition
    # garbage: a successful run always renames its staging dir away.
    for stale in out_root.glob(".staging-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
            logger.info("export: removed stale staging dir %s", stale.name)

    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=out_root))
    try:
        counts: dict[str, int] = {}
        for table in TABLES:
            rows = fetch_table(
                http, supabase_url=supabase_url, service_key=service_key, table=table
            )
            path = staging / f"{table}.json"
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
            except OSError as e:
                raise ExportError(f"write {path} failed: {e}") from e
            counts[table] = len(rows)
            logger.info("export: %s → %d rows", table, len(rows))

        if counts.get("briefs", 0) == 0:
            # Zero briefs means the export read NOTHING real — fail (OnFailure alert
            # fires) rather than promote an empty dataset into a retention slot.
            raise ExportError(
                "export fetched 0 briefs rows — refusing to call this a backup"
            )

        manifest = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "export_date": today.isoformat(),
            "tables": counts,
            "total_rows": sum(counts.values()),
        }
        with open(staging / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)

        # Atomic promote — the ONLY step that makes this export visible/dated.
        # A same-day rerun replaces its earlier successful export.
        if dest.exists():
            shutil.rmtree(dest)
        os.rename(staging, dest)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

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
