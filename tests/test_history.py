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


# ── metric_history_monthly table kwarg ───────────────────────────────────────

class _StubHttp:
    """Minimal HTTP stub: maps URL substrings to (status, body) tuples."""

    def __init__(self, routes: dict[str, tuple[int, object]]):
        self._routes = routes

    def get(self, url: str, *, headers: dict) -> tuple[int, object]:
        for path, response in self._routes.items():
            if path in url:
                return response
        return (404, None)

    def post(self, url: str, *, headers: dict, json: object) -> tuple[int, object]:
        return (201, None)


def test_get_latest_from_monthly_table():
    http = _StubHttp(
        {"/rest/v1/metric_history_monthly?metric_id=eq.cpi_12m_avg_monthly&order=as_of.desc&limit=1":
            (200, [{"metric_id": "cpi_12m_avg_monthly", "as_of": "2026-04-01", "value": 5.2, "source": "macro_observer_seed"}])}
    )
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    row = client.get_latest("cpi_12m_avg_monthly", table="metric_history_monthly")
    assert row is not None
    assert row.metric_id == "cpi_12m_avg_monthly"
    assert row.value == 5.2
    assert row.as_of.isoformat() == "2026-04-01"


# ── get_at_or_before ─────────────────────────────────────────────────────────


def test_get_at_or_before_returns_the_row_in_force_on_that_date():
    """P0 honesty fix (2026-08-22 audit #204): pairing the repo rate AS OF an
    inflation reading's date, not today's, so a Jun inflation print pairs with
    the Jun rate even after a later cut."""
    http = _StubHttp(
        {"/rest/v1/metric_history?metric_id=eq.policy_rate_repo&as_of=lte.2026-06-30&order=as_of.desc&limit=1":
            (200, [{"metric_id": "policy_rate_repo", "as_of": "2026-06-30", "value": 10.0, "source": "BB"}])}
    )
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    row = client.get_at_or_before("policy_rate_repo", date(2026, 6, 30))
    assert row is not None
    assert row.value == 10.0
    assert row.as_of == date(2026, 6, 30)


def test_get_at_or_before_returns_none_when_no_row_exists_that_early():
    http = _StubHttp({})
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    assert client.get_at_or_before("policy_rate_repo", date(2020, 1, 1)) is None


def test_get_at_or_before_accepts_a_table_kwarg():
    http = _StubHttp(
        {"/rest/v1/metric_history_monthly?metric_id=eq.x&as_of=lte.2026-06-30&order=as_of.desc&limit=1":
            (200, [{"metric_id": "x", "as_of": "2026-06-01", "value": 1.0, "source": "s"}])}
    )
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    row = client.get_at_or_before("x", date(2026, 6, 30), table="metric_history_monthly")
    assert row is not None
    assert row.as_of == date(2026, 6, 1)


def test_get_history_window_from_monthly_table():
    http = _StubHttp(
        {"/rest/v1/metric_history_monthly?metric_id=in.(cpi_12m_avg_monthly)&order=as_of.desc&limit=60":
            (200, [
                {"metric_id": "cpi_12m_avg_monthly", "as_of": "2026-04-01", "value": 5.2, "source": "x"},
                {"metric_id": "cpi_12m_avg_monthly", "as_of": "2026-03-01", "value": 5.4, "source": "x"},
            ])}
    )
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    rows = client.get_history_window(["cpi_12m_avg_monthly"], limit=60, table="metric_history_monthly")
    assert len(rows["cpi_12m_avg_monthly"]) == 2
