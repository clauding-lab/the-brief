from datetime import date, datetime, timezone

from brief.render.v5.chrome.front_of_book import render_front_of_book
from brief.schema import BankerReadInsight, Metric, NewsItem, SectionData


def _iranwar_section():
    return SectionData(
        id="iranwar",
        title="Risk premium — not scarcity.",
        kicker="Iran · Oil",
        tldr="Hormuz incident; Brent +3.7%; war-risk premia +18%.",
        metrics=[
            Metric(id="brent_spot", label="Brent spot", value=95.10, unit="USD/bbl",
                   as_of=date(2026, 4, 21), source="Yahoo", cadence="daily"),
            Metric(id="wti_spot",   label="WTI spot",   value=91.00, unit="USD/bbl",
                   as_of=date(2026, 4, 21), source="Yahoo", cadence="daily"),
        ],
        news=[],
        freshness="fresh",
        bankerread=BankerReadInsight(
            variant="full",
            meaning="m" * 80,
            action="Add scenario provisions on aviation and bunker exposure above BDT 50cr; stress at Brent $115.",
            trigger="A confirmed strait closure or second incident puts CPI feed-through within 6 weeks.",
            focus="f" * 80,
            pull_quote="This morning's move is risk premium, not scarcity — but price the next incident before it happens.",
            generated_at=datetime.now(timezone.utc),
        ),
    )


def test_front_of_book_renders_structured_preview():
    section = _iranwar_section()
    html = render_front_of_book(section, section_n="08")
    assert "§08" in html
    assert "Iran · Oil" in html
    assert "Risk premium" in html
    assert "95.10" in html
    assert "91.00" in html
    assert "Add scenario provisions" in html
    assert "confirmed strait closure" in html
    assert 'href="#section-iranwar"' in html
    assert "JUMP TO §08" in html


def test_front_of_book_handles_missing_bankerread():
    section = _iranwar_section()
    section_no_br = section.model_copy(update={"bankerread": None})
    html = render_front_of_book(section_no_br, section_n="08")
    assert "§08" in html
    assert "95.10" in html
    assert "Add scenario provisions" not in html
