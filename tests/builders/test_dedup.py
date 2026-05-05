"""Unit tests for filter_headlines — bans re-runs against the last N issues."""
from brief.builders.dedup import filter_headlines


def test_drops_exact_match():
    """Identical headline + URL in last_5_issues_news → dropped."""
    candidates = [
        {"headline": "X happened", "source_url": "https://x.com/1"},
        {"headline": "Y happened", "source_url": "https://y.com/1"},
    ]
    last_5 = [{"headline": "X happened", "source_url": "https://x.com/1"}]
    out, dropped = filter_headlines(candidates, last_5)
    assert len(out) == 1
    assert out[0]["headline"] == "Y happened"
    assert dropped == 1


def test_drops_normalized_match():
    """Different case/punctuation but same content → dropped."""
    candidates = [{"headline": "X HAPPENED!!", "source_url": "https://x.com/1"}]
    last_5 = [{"headline": "x happened", "source_url": "https://x.com/1"}]
    out, dropped = filter_headlines(candidates, last_5)
    assert out == []
    assert dropped == 1


def test_keeps_same_headline_different_url():
    """Same headline text + different URL → kept (likely a fresh follow-up)."""
    candidates = [{"headline": "X happened", "source_url": "https://x.com/2"}]
    last_5 = [{"headline": "X happened", "source_url": "https://x.com/1"}]
    out, dropped = filter_headlines(candidates, last_5)
    assert len(out) == 1
    assert dropped == 0


def test_empty_history_keeps_all():
    """No history (cold start) → return everything unfiltered."""
    candidates = [
        {"headline": "X", "source_url": "u1"},
        {"headline": "Y", "source_url": "u2"},
    ]
    out, dropped = filter_headlines(candidates, [])
    assert len(out) == 2
    assert dropped == 0


def test_preserves_order():
    """Output order matches input order for kept items."""
    candidates = [
        {"headline": "A", "source_url": "ua"},
        {"headline": "B", "source_url": "ub"},
        {"headline": "C", "source_url": "uc"},
    ]
    last_5 = [{"headline": "B", "source_url": "ub"}]
    out, _ = filter_headlines(candidates, last_5)
    assert [x["headline"] for x in out] == ["A", "C"]
