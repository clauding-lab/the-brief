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


# ── get_history_window ───────────────────────────────────────────────────────

def test_get_history_window_returns_chronological_values_per_id():
    mock = MagicMock()
    # PostgREST returns rows sorted by metric_id, as_of asc
    mock.get.return_value = (200, [
        {"metric_id": "a", "as_of": "2026-04-18", "value": 1.0},
        {"metric_id": "a", "as_of": "2026-04-19", "value": 2.0},
        {"metric_id": "a", "as_of": "2026-04-20", "value": 3.0},
        {"metric_id": "b", "as_of": "2026-04-19", "value": 10.0},
        {"metric_id": "b", "as_of": "2026-04-20", "value": 11.0},
    ])
    c = _client(mock)
    result = c.get_history_window(["a", "b"], days=14, today=date(2026, 4, 20))
    assert result == {"a": [1.0, 2.0, 3.0], "b": [10.0, 11.0]}
    mock.get.assert_called_once()
    # Verify URL embeds the in.() filter and gte cutoff
    url_arg = mock.get.call_args.args[0]
    assert "metric_id=in." in url_arg
    assert "as_of=gte.2026-04-06" in url_arg  # 20 - 14 = day 6


def test_get_history_window_filters_non_numeric_values():
    mock = MagicMock()
    mock.get.return_value = (200, [
        {"metric_id": "a", "as_of": "2026-04-19", "value": 1.0},
        {"metric_id": "a", "as_of": "2026-04-20", "value": "string-not-numeric"},
        {"metric_id": "a", "as_of": "2026-04-21", "value": None},
        {"metric_id": "a", "as_of": "2026-04-22", "value": 4.0},
    ])
    c = _client(mock)
    result = c.get_history_window(["a"], today=date(2026, 4, 22))
    assert result == {"a": [1.0, 4.0]}


def test_get_history_window_empty_input_no_http_call():
    mock = MagicMock()
    c = _client(mock)
    assert c.get_history_window([]) == {}
    mock.get.assert_not_called()


def test_get_history_window_returns_empty_on_http_error():
    mock = MagicMock()
    mock.get.return_value = (500, None)
    c = _client(mock)
    assert c.get_history_window(["a"], today=date(2026, 4, 22)) == {}
