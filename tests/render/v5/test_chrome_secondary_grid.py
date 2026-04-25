from brief.render.v5.chrome.secondary_grid import render_secondary_grid
from brief.schema import GridEntry, MapPoint, SectionData, TopPicks


def _seven_sections():
    return {
        "banking": SectionData(id="banking", title="Banking Sector", kicker="Banking",
                               tldr="", metrics=[], news=[], freshness="warning"),
        "comm":    SectionData(id="comm", title="Commodities", kicker="Comm",
                               tldr="", metrics=[], news=[], freshness="stale"),
        "fiscal":  SectionData(id="fiscal", title="Fiscal", kicker="Fiscal",
                               tldr="", metrics=[], news=[], freshness="stale"),
        "nbr":     SectionData(id="nbr", title="NBR Tax", kicker="NBR",
                               tldr="", metrics=[], news=[], freshness="warming_up"),
        "dam":     SectionData(id="dam", title="Domestic Food Prices", kicker="DAM",
                               tldr="", metrics=[], news=[], freshness="fresh"),
        "headlines": SectionData(id="headlines", title="Headlines", kicker="Headlines",
                                 tldr="", metrics=[], news=[], freshness="fresh"),
        "exec":    SectionData(id="exec", title="Exec Signals", kicker="Exec",
                               tldr="", metrics=[], news=[], freshness="fresh"),
    }


def test_secondary_grid_renders_seven_cards():
    grid = [
        GridEntry(id="banking",   tldr="NPL 35.73% — historic high"),
        GridEntry(id="comm",      tldr="LNG JKM $10.4 — flat WoW"),
        GridEntry(id="fiscal",    tldr="NBR collected 2.84tn YTD"),
        GridEntry(id="nbr",       tldr="VAT 38.2bn — Mar print due Sun"),
        GridEntry(id="dam",       tldr="Onion +12% WoW"),
        GridEntry(id="headlines", tldr="9 curated stories"),
        GridEntry(id="exec",      tldr="6 prints · 3 watches"),
    ]
    plotted = [MapPoint(id="bb", x=1, y=1, r=10, kind="anchor") for _ in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="bb")

    html = render_secondary_grid(picks=picks, sections=_seven_sections())
    assert "ALSO TODAY" in html
    assert html.count('class="grid-card"') == 7
    assert "NPL 35.73%" in html
    assert "Onion +12% WoW" in html
    assert 'href="#section-banking"' in html


def test_secondary_grid_handles_unknown_id_safely():
    grid = [GridEntry(id="ghost", tldr="x") for _ in range(7)]
    plotted = [MapPoint(id="bb", x=1, y=1, r=10, kind="anchor") for _ in range(7)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="bb")
    html = render_secondary_grid(picks=picks, sections={})
    assert html.count('class="grid-card"') == 7
