"""End-to-end assemble test with bb pilot + V4 fallback for stragglers."""
from datetime import date, datetime, timezone

from brief.render.v5.assemble import assemble_v5
from brief.render.v5.templates.section_bb import render_section_bb
from brief.schema import (
    BankerReadInsight,
    Delta,
    GridEntry,
    MapPoint,
    Metric,
    SectionData,
    TodaysCall,
    TopPicks,
)


def _bb_section() -> SectionData:
    metrics = [
        Metric(id="bb_policy_rate", label="Policy Rate", value=10.0, unit="%",
               as_of=date(2026, 4, 18), source="BB", cadence="event"),
        Metric(id="bb_gross_reserves", label="Gross Reserves", value=34.12, unit="bn USD",
               as_of=date(2026, 4, 20), source="BB", cadence="weekly",
               delta=Delta(value=0.12, direction="up", window="wow")),
    ]
    return SectionData(
        id="bb", title="Governor held. Again.", kicker="Policy & rates",
        tldr="4th consecutive hold; credit growth undershooting.",
        metrics=metrics, news=[], freshness="fresh",
        bankerread=BankerReadInsight(
            variant="full",
            meaning="word " * 80, action="word " * 80,
            trigger="word " * 80, focus="word " * 80,
            pull_quote="Comfort with the real-rate gap.",
            generated_at=datetime.now(timezone.utc),
        ),
        history_values=[34.0, 34.05, 34.08, 34.10, 34.11, 34.10, 34.12],
    )


def _stub_section(id_: str, kicker: str) -> SectionData:
    return SectionData(
        id=id_, title=f"{kicker} title", kicker=kicker, tldr=f"{kicker} tldr",
        metrics=[], news=[], freshness="warming_up",
    )


def _v4_fallback(s: SectionData) -> str:
    return f'<section id="section-{s.id}" class="section-v4-stub">{s.title}</section>'


def test_assemble_v5_smoke():
    bb = _bb_section()
    others = [_stub_section(f"s{i}", f"S{i}") for i in range(13)]
    sections = [bb] + others

    plotted = [
        MapPoint(id="bb", x=1.2, y=6.0, r=24, kind="anchor"),
        MapPoint(id="s0", x=2, y=7, r=28, kind="slow"),
        MapPoint(id="s1", x=3, y=6, r=28, kind="slow"),
        MapPoint(id="s2", x=6, y=7, r=30, kind="fresh"),
        MapPoint(id="s3", x=6.5, y=4.8, r=26, kind="fresh"),
        MapPoint(id="s4", x=5, y=5.4, r=24, kind="fresh"),
        MapPoint(id="s5", x=9.4, y=9.1, r=38, kind="event"),
    ]
    grid = [GridEntry(id=f"s{i}", tldr=f"S{i} short tldr") for i in range(6, 13)]
    picks = TopPicks(plotted=plotted, grid=grid, front_of_book_id="s5")

    todays_call = TodaysCall(text="word " * 80, generated_at=datetime.now(timezone.utc))

    html = assemble_v5(
        sections=sections,
        section_renderers={"bb": render_section_bb},
        v4_renderer_fallback=_v4_fallback,
        top_picks=picks,
        todays_call=todays_call,
        live={
            "usd_bdt": 122.70, "dsex": 5232, "brent_usd": 95.10,
            "reserves_bn_usd": 34.12,
            "generated_at": datetime(2026, 4, 21, 6, 15, tzinfo=timezone.utc),
            "next_update_label": "18:00 CLOSE",
        },
        run_meta={"vol": "II", "issue": 412, "sources_used": ["BB"], "render_duration_s": 1820, "total_cost_usd": 38.0},
        today_label="Tue 21 Apr 2026",
    )

    assert "<!DOCTYPE html>" in html
    assert "live-banner" in html
    assert "masthead" in html
    assert "risk-map" in html
    assert "front-of-book" in html
    assert "secondary-grid" in html
    assert 'id="section-bb"' in html
    assert "Governor held" in html
    assert "POLICY RATE" in html
    assert "section-v4-stub" in html
    assert "colophon" in html
