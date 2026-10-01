"""R3c — every header-plus-content read is ONE snapshot (design test 7, unit level).

A same-day correction replaces an edition's children inside one database
transaction (migration 0006) and keeps the parent UUID. A reader that fetches
the header and its children in SEPARATE HTTP requests can still see the old
header next to the new children if a publication commits between the two
requests. The rule: each reader returns either the entirely old or the
entirely new edition, never a mix, and never an edition with missing children.

The fake PostgREST below commits a publication (flips revision A <-> B of issue
236) after EVERY request, the worst case for a split reader. All data is
SYNTHETIC. The real-database proof lives in the R3 rehearsal (R/fixR3c-*).
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

import brief.notifier as notifier_mod
from brief.notifier import fetch_brief_data
from brief.v6_publisher import fetch_previous_brief, fetch_recent_news

BRIEF_ID = "0b7e8a55-2f5d-4c3e-9a51-000000000236"  # SYNTHETIC
HEADER_COLUMNS = {
    "id", "issue_no", "volume", "brief_date", "published_at", "status", "read_minutes",
    "cover_metric", "created_at", "todays_call", "lens", "frame",
}


def _edition(rev: str) -> dict[str, Any]:
    """SYNTHETIC issue 236 at revision `rev`; every text field carries the revision tag.
    Section UUIDs differ per revision, exactly as a real child replacement does."""
    def sec(slug: str, ord_: int, n_metrics: int, n_news: int) -> dict[str, Any]:
        sid = f"{rev.lower()}0000000-0000-4000-8000-{ord_:012d}"
        return {
            "id": sid, "brief_id": BRIEF_ID, "slug": slug, "ord": ord_,
            "title": f"{rev}| {slug} title", "group_key": "banking",
            "metrics": [{"id": f"{sid}-m{i}", "section_id": sid, "ord": i,
                         "label": f"{rev}| metric {i}", "value": str(i)}
                        for i in reversed(range(n_metrics))],
            "news": [{"id": f"{sid}-n{i}", "section_id": sid, "ord": i,
                      "headline": f"{rev}| headline {i}", "source": f"{rev}| source",
                      "source_url": f"https://example.test/{rev}/{slug}/{i}",
                      "published_at": None}
                     for i in reversed(range(n_news))],
        }
    sections = ([sec("headlines", 1, 0, 3), sec("bb", 2, 2, 1), sec("dse", 3, 1, 0)] if rev == "A"
                else [sec("headlines", 1, 0, 2), sec("bb", 2, 3, 2), sec("fx", 4, 0, 0)])
    header = {"id": BRIEF_ID, "issue_no": 236, "volume": 1, "brief_date": "2026-09-29",
              "published_at": f"2026-09-29T02:0{0 if rev == 'A' else 5}:00+00:00",
              "status": "published", "read_minutes": 9, "cover_metric": None,
              "created_at": "2026-09-29T02:00:00+00:00", "todays_call": f"{rev}| call",
              "lens": None, "frame": None}
    return {"header": header, "sections": sections}


_OLDER = {  # SYNTHETIC earlier issue, never republished during the test
    "header": {"id": "0b7e8a55-2f5d-4c3e-9a51-000000000235", "issue_no": 235, "volume": 1,
               "brief_date": "2026-09-28", "published_at": "2026-09-28T02:00:00+00:00",
               "status": "published", "read_minutes": 9, "cover_metric": None,
               "created_at": "2026-09-28T02:00:00+00:00", "todays_call": "old| call",
               "lens": None, "frame": None},
    "sections": [{"id": "00000000-0000-4000-8000-000000000235", "slug": "headlines", "ord": 1,
                  "brief_id": "0b7e8a55-2f5d-4c3e-9a51-000000000235", "title": "old| h",
                  "group_key": "overview", "metrics": [],
                  "news": [{"id": "old-n0", "ord": 0, "headline": "old| headline",
                            "source": "old", "source_url": "https://example.test/old",
                            "section_id": "00000000-0000-4000-8000-000000000235",
                            "published_at": None}]}],
}


def _parse_select(text: str) -> dict[str, Any]:
    """'a,b,sections(c,news(d))' -> {'a': None, 'b': None, 'sections': {...}}."""
    tree: dict[str, Any] = {}
    stack = [tree]
    token = ""
    for ch in text + ",":
        if ch == "(":
            child: dict[str, Any] = {}
            stack[-1][token] = child
            stack.append(child)
            token = ""
        elif ch in ",)":
            if token:
                stack[-1][token] = None
            token = ""
            if ch == ")":
                stack.pop()
        else:
            token += ch
    return tree


def _order_key(spec: str):
    fields = [part.split(".")[0] for part in spec.split(",")]
    return lambda row: tuple(row.get(f) for f in fields)


class FlippingPostgrest:
    """Fake PostgREST that commits a publication (A <-> B) after every request."""

    def __init__(self) -> None:
        self.rev = "A"
        self.requests: list[str] = []

    def _briefs(self) -> list[dict[str, Any]]:
        return [_edition(self.rev), _OLDER]

    def _project(self, row: dict[str, Any], sel: dict[str, Any], q: dict[str, str],
                 path: str) -> dict[str, Any]:
        if "*" in sel:  # '*' means the row's own columns, never an embedded relation
            out = {k: v for k, v in row.items() if not isinstance(v, list)}
        else:
            out = {k: row[k] for k in sel if k in row and sel[k] is None}
        for name, sub in sel.items():
            if sub is None:
                continue
            kids = [k for k in row.get(name, []) if self._keep(k, q, f"{path}{name}.")]
            if f"{path}{name}.order" in q:
                kids = sorted(kids, key=_order_key(q[f"{path}{name}.order"]))
            if f"{path}{name}.limit" in q:
                kids = kids[: int(q[f"{path}{name}.limit"])]
            out[name] = [self._project(k, sub, q, f"{path}{name}.") for k in kids]
        return {k: v for k, v in out.items() if k in sel or "*" in sel}

    @staticmethod
    def _keep(row: dict[str, Any], q: dict[str, str], prefix: str) -> bool:
        for key, cond in q.items():
            if not key.startswith(prefix) or key[len(prefix):] in {"order", "limit", "select"}:
                continue
            col = key[len(prefix):]
            if "." in col:
                continue
            op, _, val = cond.partition(".")
            if op == "eq" and str(row.get(col)) != val:
                return False
            if op == "in" and str(row.get(col)) not in val.strip("()").split(","):
                return False
        return True

    def _rows(self, table: str) -> list[dict[str, Any]]:
        if table == "briefs":
            return [{**b["header"], "sections": b["sections"]} for b in self._briefs()]
        secs = [s for b in self._briefs() for s in b["sections"]]
        if table == "sections":
            return secs
        return [child for s in secs for child in s.get(table, [])]

    def answer(self, url: str) -> bytes:
        parts = urlsplit(url)
        table = parts.path.removeprefix("/rest/v1/")
        q = {k: v[0] for k, v in parse_qs(parts.query).items()}
        self.requests.append(f"{table}?{parts.query}")
        rows = [r for r in self._rows(table) if self._keep(r, q, "")]
        if "order" in q:
            orders = q["order"].split(",")
            for spec in reversed(orders):
                col, _, direction = spec.partition(".")
                rows.sort(key=lambda r: r.get(col), reverse=direction.startswith("desc"))
        if "limit" in q:
            rows = rows[: int(q["limit"])]
        sel = _parse_select(q.get("select", "*"))
        body = [self._project(r, sel, q, "") for r in rows]
        self.rev = "B" if self.rev == "A" else "A"  # a publication commits here
        return json.dumps(body).encode()


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.fixture()
def world(monkeypatch: pytest.MonkeyPatch) -> FlippingPostgrest:
    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    fake = FlippingPostgrest()

    def urlopen(req: Any, *args: Any, **kwargs: Any) -> _Resp:
        assert req.get_method() == "GET", "readers never write"
        return _Resp(fake.answer(req.full_url))

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr(notifier_mod, "urlopen", urlopen)
    return fake


def _tags(*texts: str) -> set[str]:
    return {t.split("|", 1)[0] for t in texts}


def _one_request_rooted_at_published_briefs(world: FlippingPostgrest) -> None:
    assert len(world.requests) == 1, world.requests
    only = world.requests[0]
    assert only.startswith("briefs?"), only
    assert "status=eq.published" in only, only


def test_previous_brief_is_never_a_mix_of_two_publications(world: FlippingPostgrest) -> None:
    got = fetch_previous_brief()

    assert got is not None
    header, sections = got["brief"], got["sections"]
    rev = header["todays_call"].split("|")[0]
    texts = [s["title"] for s in sections] + [m["label"] for s in sections for m in s["metrics"]] \
        + [n["headline"] for s in sections for n in s["news"]]
    assert _tags(*texts) == {rev}, f"header {rev} mixed with children {_tags(*texts)}"
    want = _edition(rev)["sections"]
    assert [(s["slug"], len(s["metrics"]), len(s["news"])) for s in sections] == \
        [(s["slug"], len(s["metrics"]), len(s["news"])) for s in want]
    _one_request_rooted_at_published_briefs(world)


def test_previous_brief_keeps_its_output_shape_and_deterministic_order(world: FlippingPostgrest) -> None:
    got = fetch_previous_brief()

    assert got is not None
    assert set(got["brief"]) == HEADER_COLUMNS  # explicit header columns, no nested key
    assert [s["ord"] for s in got["sections"]] == sorted(s["ord"] for s in got["sections"])
    for s in got["sections"]:
        assert {"id", "brief_id", "slug", "ord", "title", "metrics", "news"} <= set(s)
        assert [m["ord"] for m in s["metrics"]] == sorted(m["ord"] for m in s["metrics"])
        assert [n["ord"] for n in s["news"]] == sorted(n["ord"] for n in s["news"])
    only = world.requests[0]
    # Same newest-first rule as get_latest_brief: a historical duplicate date
    # resolves to its highest issue number, never an arbitrary row.
    assert "order=brief_date.desc,issue_no.desc" in only and "limit=1" in only
    assert not re.search(r"select=\*", only), "header columns must be explicit"


def test_previous_brief_is_none_when_nothing_is_published(world: FlippingPostgrest,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(world, "_briefs", lambda: [])
    assert fetch_previous_brief() is None


def test_recent_news_never_mixes_or_loses_a_republished_issue(world: FlippingPostgrest) -> None:
    news = fetch_recent_news(n_issues=5)

    mine = [n for n in news if not n["headline"].startswith("old|")]
    rev = next(iter(_tags(*(n["headline"] for n in mine))), None)
    assert rev in {"A", "B"}, f"issue 236's news vanished: {news}"
    assert _tags(*(n["headline"] for n in mine)) == {rev}
    assert len(mine) == sum(len(s["news"]) for s in _edition(rev)["sections"])
    assert [n for n in news if n["headline"].startswith("old|")] == \
        [{"headline": "old| headline", "source_url": "https://example.test/old"}]
    assert all(set(n) == {"headline", "source_url"} for n in news)  # output shape unchanged
    _one_request_rooted_at_published_briefs(world)
    assert "order=brief_date.desc,issue_no.desc" in world.requests[0]
    assert "limit=5" in world.requests[0]


def test_notifier_lead_story_comes_from_the_same_publication_as_its_header(
        world: FlippingPostgrest) -> None:
    brief, lead = fetch_brief_data(BRIEF_ID)

    rev = brief.todays_call.split("|")[0]
    assert lead is not None
    first = min(next(s for s in _edition(rev)["sections"] if s["slug"] == "headlines")["news"],
                key=lambda n: n["ord"])
    assert lead.headline == first["headline"], f"header {rev} with lead {lead.headline!r}"
    assert lead.source == first["source"] and lead.source_url == first["source_url"]
    assert brief.issue_no == 236 and str(brief.brief_date) == "2026-09-29"
    _one_request_rooted_at_published_briefs(world)
    assert f"id=eq.{BRIEF_ID}" in world.requests[0]


def test_notifier_has_no_lead_when_the_headlines_section_is_absent_or_empty(
        world: FlippingPostgrest, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = _edition("A")
    empty["sections"][0]["news"] = []
    monkeypatch.setattr(world, "_briefs", lambda: [empty])
    assert fetch_brief_data(BRIEF_ID)[1] is None

    none = _edition("A")
    none["sections"] = [s for s in none["sections"] if s["slug"] != "headlines"]
    monkeypatch.setattr(world, "_briefs", lambda: [none])
    assert fetch_brief_data(BRIEF_ID)[1] is None


def test_notifier_never_reads_an_unpublished_edition(world: FlippingPostgrest,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    draft = _edition("A")
    draft["header"] = {**draft["header"], "status": "draft"}
    monkeypatch.setattr(world, "_briefs", lambda: [draft])
    with pytest.raises(RuntimeError, match="not found"):
        fetch_brief_data(BRIEF_ID)
