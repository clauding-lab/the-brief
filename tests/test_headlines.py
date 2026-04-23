from unittest.mock import patch

from brief.headlines import HEADLINE_SOURCES, scrape_all, Headline


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
