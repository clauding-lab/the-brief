from brief.render._jsx import (
    attr, fmt_num, freshness_pill, bankerread_tag,
)
from brief.schema import BankerReadFreeform, BankerReadStructured


def test_attr_escapes_quotes():
    assert attr("title", 'has "quote"') == 'title="has &quot;quote&quot;"'


def test_attr_skips_none():
    assert attr("title", None) == ''


def test_fmt_num_formats_floats():
    assert fmt_num(1234.567, 2) == "1,234.57"
    assert fmt_num(None) == "—"


def test_freshness_pill_stale_adds_pill():
    out = freshness_pill("stale")
    assert "Stale" in out
    assert "pill" in out.lower()


def test_bankerread_tag_structured_joins_4_fields():
    br = BankerReadStructured(
        meaning="a.", action="b.", trigger="c.", focus="d.", pull="a.",
    )
    tag = bankerread_tag(br)
    assert "<BankerRead" in tag
    assert "insight=" in tag
    assert "a. b. c. d." in tag
    assert '"' not in tag.split("insight=")[1][1:].split('"')[0]  # no nested DQ


def test_bankerread_tag_freeform_uses_text():
    br = BankerReadFreeform(text="No fresh data; watch closely.")
    tag = bankerread_tag(br)
    assert "<BankerRead" in tag
    assert "insight=" in tag
    assert "No fresh data" in tag


def test_bankerread_tag_none_returns_empty_string():
    assert bankerread_tag(None) == ""
