"""Fake model cards cannot silently change accepted observations."""
from datetime import date

import pytest

from brief.pipeline_v6 import _enforce_observation_contract
from brief.v6_schema import BriefPayloadV6, BriefV6, MetricV6, SectionV6


def payload(value='80.25', sub='', held_from=None):
    return BriefPayloadV6(brief=BriefV6(issue_no=1, volume=1, brief_date=date(2026, 9, 25)),
        sections=[SectionV6(slug='iranwar', ord=1, title='Oil', group_key='overview',
            metrics=[MetricV6(label='Brent spot', value=value, sub=sub, held_from=held_from)])])


RAW = [{'slug': 'iranwar', 'metrics': [dict(id='iranwar_brent_spot', label='Brent spot',
    value=80.25, unit='USD/bbl', as_of='2026-09-23', source='Official quote', stale=True,
    cadence='daily', period='23 Sep 2026')]}]


@pytest.mark.parametrize('value', ['81.25', '$8.025bn', 'unavailable', '-80.25'])
def test_changed_or_erased_value_is_reprinted_from_the_observation(value):
    """R2 fix 7b (owner decision (g)): a changed or erased card number no longer
    holds the issue; it is replaced by the builder observation in the house format."""
    model = payload(value)
    _enforce_observation_contract(model, RAW)
    assert model.sections[0].metrics[0].value == '$80.25'


def test_date_and_held_explanation_are_authoritative():
    model = payload('$80.25', 'Fresh today', date(2026, 9, 25))
    _enforce_observation_contract(model, RAW)
    metric = model.sections[0].metrics[0]
    assert metric.held_from == date(2026, 9, 23)
    assert metric.sub == 'Held reading · 23 Sep 2026 · Official quote'


def test_provisional_release_cannot_be_erased():
    raw = [{'slug': 'iranwar', 'metrics': [{**RAW[0]['metrics'][0],
        'source': 'Official quote · provisional', 'stale': False}]}]
    model = payload('$80.25', 'Final September')
    _enforce_observation_contract(model, raw)
    assert 'provisional' in model.sections[0].metrics[0].sub
    assert 'Final September' not in model.sections[0].metrics[0].sub


def test_percent_alias_and_rounding_remain_valid():
    raw = [{'slug': 'iranwar', 'metrics': [{**RAW[0]['metrics'][0],
        'value': 8.666, 'unit': 'pct', 'stale': False}]}]
    model = payload('8.67%')
    _enforce_observation_contract(model, raw)
    # House format (fix 7b round 1): the source's own decimal, never rounded; an
    # unmapped unit keeps "<number> <unit>". The SPA's cleanMetricValue shows 8.66.
    assert model.sections[0].metrics[0].value == '8.666 pct'


def test_catalog_date_can_only_preserve_the_accepted_observation_date():
    raw = [{'slug': 'iranwar', 'metrics': [{**RAW[0]['metrics'][0], 'stale': False}]}]
    model = payload('$80.25', held_from=date(2026, 8, 1))
    _enforce_observation_contract(model, raw)
    assert model.sections[0].metrics[0].held_from == date(2026, 9, 23)
