from datetime import datetime, timezone

from brief.render.v5.chrome.live_banner import render_live_banner


def test_live_banner_renders_all_fields():
    html = render_live_banner({
        "usd_bdt": 122.70,
        "dsex": 5232,
        "brent_usd": 95.10,
        "reserves_bn_usd": 34.12,
        "generated_at": datetime(2026, 4, 21, 6, 15, tzinfo=timezone.utc),
        "next_update_label": "18:00 CLOSE",
    })
    assert "USD/BDT" in html
    assert "122.70" in html
    assert "DSEX" in html
    assert "5,232" in html
    assert "BRENT" in html
    assert "95.10" in html
    assert "RESERVES" in html
    assert "34.12BN" in html or "34.12 BN" in html
    assert "NEXT UPDATE" in html
    assert "18:00 CLOSE" in html
    assert 'class="live-banner"' in html


def test_live_banner_handles_missing_brent_gracefully():
    html = render_live_banner({
        "usd_bdt": 122.70,
        "dsex": 5232,
        "brent_usd": None,
        "reserves_bn_usd": 34.12,
        "generated_at": datetime(2026, 4, 21, 6, 15, tzinfo=timezone.utc),
        "next_update_label": "18:00 CLOSE",
    })
    assert 'class="live-banner"' in html
    assert "USD/BDT" in html  # other fields still render
