"""Tests for validate_headlines_layout — the V5 newspaper-layout payload."""
from __future__ import annotations

from brief.claude.validators import validate_headlines_layout


_URLS = {f"https://example.com/h{i}" for i in range(1, 11)}


def _payload(**overrides) -> dict:
    base = {
        "lead": {
            "url": "https://example.com/h1",
            "key_points": [
                "<b>Brent $95.10</b> — 6-week CPI food feed-through.",
                "Insurer <b>war-risk premia up 18%</b> — review exposure.",
                "<b>BSEC</b> policy pricing review at 10:00 BDT.",
            ],
        },
        "right_rail": [
            "https://example.com/h2",
            "https://example.com/h3",
            "https://example.com/h4",
            "https://example.com/h5",
        ],
        "secondary": [
            "https://example.com/h6",
            "https://example.com/h7",
            "https://example.com/h8",
        ],
    }
    base.update(overrides)
    return base


def test_valid_payload_accepted():
    r = validate_headlines_layout(_payload(), allowed_urls=_URLS)
    assert r.ok, r.reason
    assert r.value["lead"]["url"] == "https://example.com/h1"
    assert len(r.value["lead"]["key_points"]) == 3
    assert len(r.value["right_rail"]) == 4
    assert len(r.value["secondary"]) == 3


def test_rejects_when_payload_not_dict():
    r = validate_headlines_layout([1, 2, 3], allowed_urls=_URLS)
    assert not r.ok
    assert "dict" in r.reason


def test_rejects_unknown_lead_url():
    r = validate_headlines_layout(
        _payload(lead={"url": "https://elsewhere.com/x", "key_points": ["a", "b", "c"]}),
        allowed_urls=_URLS,
    )
    assert not r.ok
    assert "lead url" in r.reason.lower()


def test_rejects_wrong_key_points_count():
    bad_lead = {"url": "https://example.com/h1", "key_points": ["only one"]}
    r = validate_headlines_layout(_payload(lead=bad_lead), allowed_urls=_URLS)
    assert not r.ok
    assert "key_points" in r.reason


def test_rejects_non_string_key_points():
    bad_lead = {"url": "https://example.com/h1",
                "key_points": ["a", 42, "c"]}
    r = validate_headlines_layout(_payload(lead=bad_lead), allowed_urls=_URLS)
    assert not r.ok


def test_rejects_wrong_right_rail_count():
    r = validate_headlines_layout(
        _payload(right_rail=["https://example.com/h2", "https://example.com/h3"]),
        allowed_urls=_URLS,
    )
    assert not r.ok
    assert "right_rail" in r.reason


def test_rejects_wrong_secondary_count():
    r = validate_headlines_layout(
        _payload(secondary=["https://example.com/h6", "https://example.com/h7"]),
        allowed_urls=_URLS,
    )
    assert not r.ok
    assert "secondary" in r.reason


def test_rejects_unknown_right_rail_url():
    r = validate_headlines_layout(
        _payload(right_rail=[
            "https://example.com/h2",
            "https://nope.com/x",
            "https://example.com/h4",
            "https://example.com/h5",
        ]),
        allowed_urls=_URLS,
    )
    assert not r.ok
    assert "url" in r.reason.lower()


def test_rejects_duplicate_url_across_buckets():
    r = validate_headlines_layout(
        _payload(secondary=[
            "https://example.com/h1",  # also the lead
            "https://example.com/h7",
            "https://example.com/h8",
        ]),
        allowed_urls=_URLS,
    )
    assert not r.ok
    assert "duplicate" in r.reason.lower()


def test_rejects_oversized_key_point():
    bigword = "x " * 30  # 30 words
    bad_lead = {"url": "https://example.com/h1",
                "key_points": [bigword, "ok", "ok"]}
    r = validate_headlines_layout(_payload(lead=bad_lead), allowed_urls=_URLS)
    assert not r.ok
    assert "key_point" in r.reason.lower()
