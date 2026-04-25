from unittest.mock import patch, MagicMock, call
import urllib.request

from brief.headlines import HEADLINE_SOURCES, scrape_all, Headline, BROWSER_UA


def test_sources_are_three():
    codes = [s["code"] for s in HEADLINE_SOURCES]
    assert codes == ["DS", "TBS", "FE"]


def test_scrape_all_returns_flat_list():
    ds_html = (
        '<a href="/business/one-long-title-here-about-economy">'
        'One long title here about economy</a>'
        '<a href="/business/two-long-title-here-about-markets">'
        'Two long title here about markets</a>'
    )

    def fake_fetch(url, _timeout=15):
        return ds_html if "thedailystar.net" in url else ""

    with patch("brief.headlines._fetch_page", side_effect=fake_fetch):
        result = scrape_all(count_per_source=2)

    assert all(isinstance(h, Headline) for h in result)
    titles = [h.title for h in result if h.source == "DS"]
    assert len(titles) == 2
    assert "about economy" in titles[0]


def test_scrape_all_tolerates_fetch_failure():
    with patch("brief.headlines._fetch_page", return_value=""):
        result = scrape_all(count_per_source=2)
    assert result == []


# ── Fix 1: Browser User-Agent ────────────────────────────────────────────────

def test_browser_ua_constant_starts_with_mozilla():
    """BROWSER_UA must look like a real browser, not a bot string."""
    assert BROWSER_UA.startswith("Mozilla/5.0"), (
        f"Expected BROWSER_UA to start with 'Mozilla/5.0', got: {BROWSER_UA!r}"
    )


def test_browser_ua_includes_chrome_token():
    """Realistic Chrome UA is needed to pass Cloudflare / ASN UA checks."""
    assert "Chrome" in BROWSER_UA, (
        f"Expected 'Chrome' in BROWSER_UA, got: {BROWSER_UA!r}"
    )


def test_fetch_page_sends_browser_ua(monkeypatch):
    """_fetch_page must attach BROWSER_UA as the User-Agent header."""
    captured_headers = {}

    original_request = urllib.request.Request

    def capturing_request(url, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return original_request(url, headers=headers, **kwargs)

    fake_response = MagicMock()
    fake_response.__enter__ = lambda s: s
    fake_response.__exit__ = MagicMock(return_value=False)
    fake_response.read.return_value = b"<html>ok</html>"

    monkeypatch.setattr(urllib.request, "Request", capturing_request)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: fake_response)

    # Import _fetch_page — it is pragma: no cover but we test via monkeypatch
    from brief.headlines import _fetch_page
    _fetch_page("https://example.com")

    ua = captured_headers.get("User-Agent", "")
    assert ua.startswith("Mozilla/5.0"), (
        f"User-Agent header sent was: {ua!r}. Expected it to start with 'Mozilla/5.0'."
    )
    assert "Chrome" in ua, (
        f"User-Agent header sent was: {ua!r}. Expected 'Chrome' token."
    )


# ── Fix 2: No stale businessstandardbd.com in source list ───────────────────

def test_source_list_has_no_businessstandardbd():
    """businessstandardbd.com is NXDOMAIN — must not appear in HEADLINE_SOURCES."""
    all_urls = " ".join(s["url"] for s in HEADLINE_SOURCES)
    assert "businessstandardbd.com" not in all_urls, (
        "businessstandardbd.com (NXDOMAIN) found in HEADLINE_SOURCES — remove it."
    )


def test_source_list_contains_tbsnews():
    """tbsnews.net (TBS News) must be present in HEADLINE_SOURCES as replacement."""
    all_urls = " ".join(s["url"] for s in HEADLINE_SOURCES)
    assert "tbsnews.net" in all_urls, (
        "tbsnews.net not found in HEADLINE_SOURCES — it should be the TBS entry."
    )
