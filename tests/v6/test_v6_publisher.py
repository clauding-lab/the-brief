"""V6 publisher tests — mocked urllib, no network calls."""
from __future__ import annotations

from brief.publication_identity import PublishIdentity

import io
import json
from unittest.mock import patch

import pytest

from brief.v6_publisher import (
    PublishError,
    fetch_max_issue_no,
    fetch_previous_brief,
    publish_brief,
)
from brief.v6_schema import BriefPayloadV6


@pytest.fixture(autouse=True)
def _supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")


def _fake_response(payload: object) -> io.BytesIO:
    body = json.dumps(payload).encode("utf-8")
    resp = io.BytesIO(body)
    return resp


def _minimal_payload(issue_no: int = 89) -> BriefPayloadV6:
    return BriefPayloadV6.model_validate(
        {
            "brief": {
                "issue_no": issue_no,
                "volume": 1,
                "brief_date": "2026-05-05",
                "todays_call": "Test brief.",
                "status": "published",
            },
            "sections": [
                {
                    "slug": "bb",
                    "ord": 3,
                    "title": "Bangladesh Bank",
                    "group_key": "banking",
                    "weight": 1,
                    "metrics": [
                        {"label": "Repo", "value": "10.00%", "tone": "neu"},
                    ],
                    "news": [
                        {"headline": "BB holds policy rates", "source": "DS"},
                    ],
                }
            ],
        }
    )


def test_missing_env_raises() -> None:
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(PublishError, match="Missing SUPABASE_URL"):
            fetch_max_issue_no()


def test_fetch_max_issue_no_empty_table() -> None:
    """fetch_max_issue_no returns 0 when the table is empty."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _fake_response([])
        assert fetch_max_issue_no() == 0


def test_fetch_max_issue_no_with_data() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _fake_response(
            [{"issue_no": 88}]
        )
        assert fetch_max_issue_no() == 88


def test_fetch_previous_brief_none() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _fake_response([])
        assert fetch_previous_brief() is None


def _capture_urlopen(captured_calls, *, fail_on=None):  # type: ignore[no-untyped-def]
    """Build a urlopen side_effect that records (method, url, body) per call and
    routes canned PostgREST replies. `fail_on=(method, url_substr)` raises a 500
    HTTPError on the matching call (to exercise partial-failure paths)."""
    import urllib.error

    def _side(req, *args, **kwargs):  # type: ignore[no-untyped-def]
        url = req.full_url
        method = req.get_method()
        body = json.loads(req.data.decode()) if req.data else None
        captured_calls.append((method, url, body))

        if fail_on is not None and method == fail_on[0] and fail_on[1] in url:
            raise urllib.error.HTTPError(
                url=url, code=500, msg="Internal Server Error",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"message":"child insert failed"}'),
            )

        class _Resp:
            def __enter__(self):
                if method == "DELETE":
                    return _fake_response(None)
                if "/briefs" in url and method == "POST":
                    row = body[0] if isinstance(body, list) else body
                    return _fake_response([{"id": "brief-uuid-1", **row}])
                if "/sections" in url and method == "POST":
                    return _fake_response([{"id": "section-uuid-1", **body}])
                # PATCH flip, metric/news POSTs → 204-style empty
                return _fake_response(None)

            def __exit__(self, *a, **k):
                return False

        return _Resp()

    return _side


def test_publish_brief_atomic_flow() -> None:
    """Two-phase (landmine 22): DELETE issue → sweep stale drafts → POST brief AS
    DRAFT → children → PATCH status='published' as the LAST call."""
    payload = _minimal_payload(issue_no=89)
    captured_calls: list[tuple[str, str, object | None]] = []

    with patch("urllib.request.urlopen", side_effect=_capture_urlopen(captured_calls)):
        brief_id = publish_brief(payload, expected_identity=PublishIdentity(payload.brief.issue_no, payload.brief.brief_date))

    assert brief_id == "brief-uuid-1"

    assert captured_calls[0][0] == "GET"
    assert "issue_no=eq.89" in captured_calls[0][1]
    captured_calls = captured_calls[1:]
    methods = [c[0] for c in captured_calls]
    assert methods[0] == "DELETE"  # idempotency: delete this issue first
    assert "/briefs?issue_no=eq.89" in captured_calls[0][1]
    assert methods[1] == "DELETE"  # then sweep stale drafts of OTHER issues
    assert "status=eq.draft" in captured_calls[1][1]
    assert "created_at=lt." in captured_calls[1][1]
    assert methods[2] == "POST"  # then insert brief

    # The brief is inserted as a DRAFT — invisible to get_latest_brief until the flip
    inserted_brief = captured_calls[2][2]
    assert inserted_brief["issue_no"] == 89  # type: ignore[index]
    assert inserted_brief["todays_call"] == "Test brief."  # type: ignore[index]
    assert inserted_brief["status"] == "draft"  # type: ignore[index]

    # The LAST call is the atomic flip to published (the only visibility-granting write)
    last_method, last_url, last_body = captured_calls[-1]
    assert last_method == "PATCH"
    assert "/briefs?id=eq.brief-uuid-1" in last_url
    assert last_body == {"status": "published"}  # type: ignore[comparison-overlap]
    # Exactly one flip, and no earlier call published anything
    assert sum(1 for c in captured_calls if c[0] == "PATCH") == 1


def test_publish_brief_sweep_failure_is_non_fatal() -> None:
    """The stale-draft sweep is best-effort: if its DELETE fails, today's publish
    must proceed normally (review LOW follow-up on the two-phase fix)."""
    payload = _minimal_payload(issue_no=91)
    captured_calls: list[tuple[str, str, object | None]] = []

    side = _capture_urlopen(captured_calls, fail_on=("DELETE", "status=eq.draft"))
    with patch("urllib.request.urlopen", side_effect=side):
        brief_id = publish_brief(payload, expected_identity=PublishIdentity(payload.brief.issue_no, payload.brief.brief_date))  # must NOT raise

    assert brief_id == "brief-uuid-1"
    # Flip still happened — the publish completed despite the failed sweep
    assert captured_calls[-1][0] == "PATCH"
    assert captured_calls[-1][2] == {"status": "published"}


def test_publish_brief_stays_draft_when_child_post_fails() -> None:
    """Regression (landmine 22 / #118): if a child POST fails AFTER the brief row
    is inserted, publish_brief must raise AND never flip status to 'published' —
    the half-written brief stays a draft, invisible to get_latest_brief."""
    payload = _minimal_payload(issue_no=90)
    captured_calls: list[tuple[str, str, object | None]] = []

    # Fail on the metrics child POST (after DELETE, briefs INSERT, sections INSERT)
    side = _capture_urlopen(captured_calls, fail_on=("POST", "/metrics"))
    with patch("urllib.request.urlopen", side_effect=side):
        with pytest.raises(PublishError, match="HTTP 500"):
            publish_brief(payload, expected_identity=PublishIdentity(payload.brief.issue_no, payload.brief.brief_date))

    # The brief row WAS inserted, but as a draft
    brief_posts = [c for c in captured_calls if c[0] == "POST" and "/briefs" in c[1]]
    assert brief_posts, "brief row should have been inserted before the child failure"
    assert brief_posts[0][2]["status"] == "draft"  # type: ignore[index]
    # Critically: the status flip NEVER happened → no published half-brief
    assert not any(c[0] == "PATCH" for c in captured_calls), (
        "partial failure must not flip the brief to published"
    )


def test_publish_brief_propagates_http_error() -> None:
    """A 500 from Supabase should raise PublishError, not silently succeed.

    side_effect raises on EVERY call, so the FIRST call (DELETE) fails — the safe
    case where nothing is written. (Partial-failure-after-insert is covered by
    test_publish_brief_stays_draft_when_child_post_fails.)"""
    import urllib.error

    payload = _minimal_payload()
    err = urllib.error.HTTPError(
        url="https://test.supabase.co/rest/v1/briefs",
        code=500,
        msg="Internal Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b'{"message":"oops"}'),
    )

    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(PublishError, match="HTTP 500"):
            publish_brief(payload, expected_identity=PublishIdentity(payload.brief.issue_no, payload.brief.brief_date))


def test_model_issue_one_april20_cannot_delete_when_max_is_235():
    from datetime import date
    from brief.publication_identity import resolve_identity

    expected = resolve_identity(date(2026, 9, 25), same_day_rows=[], max_issue_no=235)
    payload = _minimal_payload(issue_no=1)
    payload.brief.brief_date = date(2026, 4, 20)
    with patch("brief.v6_publisher._request") as request:
        with pytest.raises(PublishError, match="trusted publication identity"):
            publish_brief(payload, expected_identity=expected)
    request.assert_not_called()  # zero GET/DELETE/POST/PATCH, before config/network


def test_target_date_is_rechecked_before_any_delete():
    from datetime import date

    payload = _minimal_payload(issue_no=235)
    with patch("brief.v6_publisher._request", return_value=[
        {"issue_no": 235, "brief_date": "2026-04-20"},
    ]) as request:
        with pytest.raises(PublishError, match="Existing target conflicts"):
            publish_brief(payload, expected_identity=PublishIdentity(235, date(2026, 5, 5)))
    assert [c.args[0] for c in request.call_args_list] == ["GET"]
    assert "issue_no=eq.235" in request.call_args.args[1]


def test_publisher_requires_trusted_identity():
    with patch("brief.v6_publisher._request") as request:
        with pytest.raises(TypeError, match="expected_identity"):
            publish_brief(_minimal_payload())
    request.assert_not_called()


def test_same_day_read_includes_drafts_and_published_rows():
    from datetime import date
    from brief.v6_publisher import fetch_same_day_briefs

    with patch("brief.v6_publisher._request", return_value=[]) as request:
        assert fetch_same_day_briefs(date(2026, 9, 25)) == []
    assert request.call_args.args == (
        "GET", "/briefs?brief_date=eq.2026-09-25&select=issue_no,brief_date,status",
    )
