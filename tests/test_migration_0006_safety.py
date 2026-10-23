"""Migration 0006 keeps its publication-safety properties (R3d; AGENTS.md landmine 41).

The atomic publisher's guarantees live in SQL that CI cannot execute (it needs the
PostgreSQL 17.6 + PostgREST rehearsal clone, C/r3-rehearsal). These static checks pin the
properties a later edit could silently weaken:

- the writer runs with the CALLER's rights (SECURITY INVOKER, never DEFINER), VOLATILE, with a
  fixed empty search_path;
- only service_role may execute it; the public roles lose every table-write privilege
  (owner decision (b), 26 Sep 2026);
- one transaction, no swallowed errors: no EXCEPTION handler, COMMIT, ROLLBACK or SAVEPOINT
  inside the function, so any failure rolls the whole edition back;
- it never deletes a parent `briefs` row (the old DELETE+POST gap), serialises on a
  transaction advisory lock, and flips `status = 'published'` as its LAST write.

Static reads of migrations/0006_publish_brief_atomic.sql only; nothing touches a database.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "0006_publish_brief_atomic.sql"
FUNCTION = "public.publish_brief_atomic(integer, date, jsonb)"
PUBLIC_ROLES = ("PUBLIC", "anon", "authenticated")
TABLES = ("briefs", "sections", "metrics", "news", "chart_series", "chart_notes")
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES", "MAINTAIN")


def _sql_without_comments(text: str) -> str:
    """Drop `--` comments and the COMMENT ON literal so prose cannot satisfy or trip a check."""
    code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    return re.sub(r"^COMMENT ON FUNCTION .*?';$", "", code, flags=re.DOTALL | re.MULTILINE)


@pytest.fixture(scope="module")
def sql() -> str:
    return _sql_without_comments(MIGRATION.read_text())


@pytest.fixture(scope="module")
def header_and_body(sql: str) -> tuple[str, str]:
    """(CREATE FUNCTION header up to AS, function body between the $fn$ quotes)."""
    match = re.search(r"CREATE OR REPLACE FUNCTION public\.publish_brief_atomic\((.*?)\$fn\$(.*?)\$fn\$;",
                      sql, flags=re.DOTALL)
    assert match, "publish_brief_atomic definition not found"
    return match.group(1), match.group(2)


def test_whole_migration_is_one_transaction_that_reloads_the_api_schema(sql: str) -> None:
    statements = [s.strip() for s in sql.split("\n") if s.strip()]
    assert statements[0] == "BEGIN;" and statements[-1] == "COMMIT;"
    assert "NOTIFY pgrst, 'reload schema';" in sql


def test_writer_runs_with_the_callers_rights_and_a_fixed_search_path(header_and_body: tuple[str, str]) -> None:
    header, _ = header_and_body
    assert re.search(r"\bVOLATILE\b", header)
    assert re.search(r"\bSECURITY INVOKER\b", header)
    assert "DEFINER" not in header
    assert re.search(r"SET search_path = ''", header)


def test_only_service_role_may_execute_the_writer(sql: str) -> None:
    revoke = re.search(rf"REVOKE ALL ON FUNCTION {re.escape(FUNCTION)} FROM ([^;]+);", sql)
    assert revoke and {r.strip() for r in revoke.group(1).split(",")} >= set(PUBLIC_ROLES)
    grants = re.findall(r"GRANT\s+([^;]*?)\s+ON FUNCTION public\.publish_brief_atomic\b[^;]*?TO ([^;]+);", sql)
    assert grants == [("EXECUTE", "service_role")]
    assert "SECURITY DEFINER" not in sql


def test_public_roles_lose_every_table_write_privilege(sql: str) -> None:
    match = re.search(r"REVOKE ([A-Z, ]+)\s+ON TABLE ([^;]+?)\s+FROM ([^;]+);", sql)
    assert match, "table-privilege REVOKE not found"
    privileges = {p.strip() for p in match.group(1).split(",")}
    tables = {t.strip().removeprefix("public.") for t in match.group(2).split(",")}
    roles = {r.strip() for r in match.group(3).split(",")}
    assert privileges >= set(WRITE_PRIVILEGES)
    assert tables == set(TABLES)
    assert roles >= {"anon", "authenticated"}


def test_no_error_is_swallowed_and_no_transaction_control_inside_the_writer(
        header_and_body: tuple[str, str]) -> None:
    _, body = header_and_body
    for forbidden in (r"\bEXCEPTION\s+WHEN\b", r"\bCOMMIT\b", r"\bROLLBACK\b", r"\bSAVEPOINT\b"):
        assert not re.search(forbidden, body, flags=re.IGNORECASE), forbidden


def test_writer_never_deletes_an_edition_and_serialises_on_one_lock(header_and_body: tuple[str, str]) -> None:
    _, body = header_and_body
    # SQL keywords are case-insensitive: a lowercase `delete from public.briefs` is the same gap.
    assert not re.search(r"DELETE\s+FROM\s+public\.briefs\b", body, flags=re.IGNORECASE)
    deletes = re.findall(r"DELETE\s+FROM\s+public\.(\w+)\s+WHERE\s+([^;]+);", body, flags=re.IGNORECASE)
    assert deletes == [("sections", "brief_id = v_brief_id")]
    assert re.search(r"pg_advisory_xact_lock\(", body)


def test_published_flip_is_the_last_write(header_and_body: tuple[str, str]) -> None:
    _, body = header_and_body
    flip = re.search(r"SET status = 'published'", body)
    assert flip, "published flip not found"
    writes = [m.start() for m in re.finditer(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+public\.", body,
                                             flags=re.IGNORECASE)]
    assert writes and max(writes) < flip.start()
    assert body.count("status = 'published'") == 1


# R3d controller close (2 Oct 2026): the adversarial r0 reviewer moved the lock below every write,
# and added a TRUNCATE inside the writer; both passed (fixR3d-adversarial-r0/static_test_mutants.py).
def test_lock_is_taken_before_the_first_write_and_the_writer_never_truncates(
        header_and_body: tuple[str, str]) -> None:
    _, body = header_and_body
    lock = re.search(r"pg_advisory_xact_lock\(", body)
    first_write = re.search(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+public\.", body, flags=re.IGNORECASE)
    assert lock and first_write and lock.start() < first_write.start()
    assert not re.search(r"\bTRUNCATE\b", body, flags=re.IGNORECASE)
