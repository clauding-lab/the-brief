"""V6 publisher tests — mocked urllib, no network calls."""
from __future__ import annotations

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


def test_publish_brief_atomic_flow() -> None:
    """publish_brief should: DELETE by issue_no → POST brief → POST sections → POST children."""
    payload = _minimal_payload(issue_no=89)
    captured_calls: list[tuple[str, str, object | None]] = []

    def _capture(req, *args, **kwargs):  # type: ignore[no-untyped-def]
        url = req.full_url
        method = req.get_method()
        body = json.loads(req.data.decode()) if req.data else None
        captured_calls.append((method, url, body))

        # DELETE returns nothing; POST briefs/sections returns single row with id;
        # POST metrics/news returns nothing (we don't request representation)
        class _Resp:
            def __enter__(self):
                if method == "DELETE":
                    return _fake_response(None)
                if "/briefs" in url and method == "POST":
                    row = body[0] if isinstance(body, list) else body
                    return _fake_response([{"id": "brief-uuid-1", **row}])
                if "/sections" in url and method == "POST":
                    return _fake_response([{"id": "section-uuid-1", **body}])
                return _fake_response(None)

            def __exit__(self, *a, **k):
                return False

        return _Resp()

    with patch("urllib.request.urlopen", side_effect=_capture):
        brief_id = publish_brief(payload)

    assert brief_id == "brief-uuid-1"

    methods = [c[0] for c in captured_calls]
    assert methods[0] == "DELETE"  # idempotency: delete first
    assert methods[1] == "POST"  # then insert brief
    assert "/briefs?issue_no=eq.89" in captured_calls[0][1]

    inserted_brief = captured_calls[1][2]
    assert inserted_brief["issue_no"] == 89  # type: ignore[index]
    assert inserted_brief["todays_call"] == "Test brief."  # type: ignore[index]


def test_publish_brief_propagates_http_error() -> None:
    """A 500 from Supabase should raise PublishError, not silently succeed."""
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
            publish_brief(payload)
