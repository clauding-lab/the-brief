"""Schema tests for F4 MoverRowV6 + SectionV6.movers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from brief.v6_schema import MoverRowV6, SectionV6


def _section(**over):
    base = dict(slug="dse", ord=5, title="DSE Markets", group_key="markets", weight=1)
    base.update(over)
    return SectionV6(**base)


def test_mover_row_fields():
    m = MoverRowV6(ticker="FINEFOODS", price=577.0, return_pct=16.59)
    assert (m.ticker, m.price, m.return_pct) == ("FINEFOODS", 577.0, 16.59)


def test_section_accepts_movers_list():
    s = _section(movers=[{"ticker": "GP", "price": 300.0, "return_pct": -2.5}])
    assert s.movers is not None and s.movers[0].ticker == "GP"


def test_section_movers_defaults_none():
    assert _section().movers is None


def test_section_still_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _section(bogus_field=123)


def test_mover_row_ignores_unknown_field():
    m = MoverRowV6(ticker="GP", price=300.0, return_pct=-2.5, bogus="x")
    assert not hasattr(m, "bogus")


def test_mover_row_rejects_empty_ticker():
    with pytest.raises(ValidationError):
        MoverRowV6(ticker="", price=1.0, return_pct=0.0)
