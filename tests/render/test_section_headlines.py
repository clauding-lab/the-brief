from datetime import datetime, timezone

from brief.render.templates.section_headlines import render
from brief.schema import NewsItem, SectionData


def _section():
    return SectionData(
        id="headlines", title="Headlines", freshness="fresh",
        news=[
            NewsItem(title="BB holds rate", url="https://x/1",
                     source="DS", published=datetime(2026, 4, 21, tzinfo=timezone.utc)),
            NewsItem(title='Budget "big" day', url="https://x/2",
                     source="TBS", published=datetime(2026, 4, 21, tzinfo=timezone.utc)),
        ],
    )


def test_headlines_render_escapes_quotes():
    out = render(_section())
    assert out.startswith("function SectionHeadlines()")
    assert "BB holds rate" in out
    assert "&quot;big&quot;" in out
    assert "https://x/1" in out
