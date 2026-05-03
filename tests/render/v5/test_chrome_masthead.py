from datetime import datetime, timezone

from brief.render.v5.chrome.masthead import render_masthead
from brief.schema import TodaysCall


def test_masthead_renders_volume_issue_date_title_dek_todays_call():
    tc = TodaysCall(
        text="Hormuz is priced risk, not scarcity. With food CPI sticky at 10.4% and reserves flat-not-building, the margin for a second incident is narrower than it looks. Hedge the oil book — not the headline.",
        generated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
    )
    html = render_masthead(
        vol="II",
        issue=412,
        today_label="Tue 21 Apr 2026",
        todays_call=tc,
    )
    assert "VOL. II" in html
    assert "NO. 412" in html
    assert "Tue 21 Apr 2026" in html
    assert "The" in html and "Brief" in html
    assert "plotted" in html
    assert "TODAY'S CALL" in html
    assert "priced risk, not scarcity" in html
    assert "Desk Editor" in html
    assert 'class="masthead"' in html


def test_masthead_escapes_call_text():
    tc = TodaysCall(text="<script>x</script> " * 8, generated_at=datetime.now(timezone.utc))
    html = render_masthead(vol="II", issue=1, today_label="x", todays_call=tc)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
