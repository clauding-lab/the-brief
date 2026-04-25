from brief.render.v5.chrome.colophon import render_colophon


def test_colophon_renders_metadata():
    html = render_colophon({
        "vol": "II",
        "issue": 412,
        "today_label": "Tue 21 Apr 2026",
        "sources_used": ["BB", "BBS", "DSE", "Yahoo"],
        "render_duration_s": 1820,
        "total_cost_usd": 38.42,
    })
    assert "VOL. II" in html
    assert "NO. 412" in html
    assert "Tue 21 Apr 2026" in html
    assert "BB" in html and "DSE" in html
    assert "30:20" in html or "30 min" in html
    assert "$38.42" in html
    assert 'class="colophon"' in html
