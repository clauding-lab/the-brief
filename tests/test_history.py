from datetime import date
from unittest.mock import MagicMock

from brief.history import MetricHistoryClient, HistoryRow


def _client(mock_http):
    return MetricHistoryClient(
        url="https://example.supabase.co",
        service_key="svc",
        http=mock_http,
    )


def test_get_latest_returns_row():
    mock = MagicMock()
    mock.get.return_value = (200, [{"metric_id": "x", "as_of": "2026-04-20",
                                    "value": 10.0, "source": "BB",
                                    "ingested_at": "2026-04-20T00:00:00Z"}])
    c = _client(mock)
    row = c.get_latest("x")
    assert row == HistoryRow(
        metric_id="x", as_of=date(2026, 4, 20), value=10.0, source="BB"
    )
    mock.get.assert_called_once()


def test_get_latest_returns_none_when_empty():
    mock = MagicMock()
    mock.get.return_value = (200, [])
    c = _client(mock)
    assert c.get_latest("x") is None


def test_upsert_many_calls_post():
    mock = MagicMock()
    mock.post.return_value = (201, None)
    c = _client(mock)
    result = c.upsert_many([
        HistoryRow("a", date(2026, 4, 20), 1, "BB"),
        HistoryRow("b", date(2026, 4, 20), 2, "BB"),
    ])
    assert result is True
    mock.post.assert_called_once()
    args, kwargs = mock.post.call_args
    body = kwargs["json"]
    assert len(body) == 2
    assert body[0]["metric_id"] == "a"


def test_upsert_many_noop_on_empty():
    mock = MagicMock()
    c = _client(mock)
    c.upsert_many([])
    mock.post.assert_not_called()
