from datetime import date

from brief.cadence import evaluate_risk_rules
from brief.schema import Metric, SectionData


def _section(id: str, metrics: list[Metric]) -> SectionData:
    return SectionData(
        id=id, title="x", kicker="x", tldr="", metrics=metrics, news=[], freshness="fresh"
    )


def test_npl_30_fires_critical():
    metric = Metric(id="banking_npl_pct", label="NPL", value=35.73, unit="%",
                    as_of=date(2026, 1, 1), source="BB", cadence="quarterly")
    fired, level, rule_id = evaluate_risk_rules(_section("banking", [metric]))
    assert fired and level == "critical" and rule_id == "banking_npl_above_30"


def test_npl_25_fires_warning():
    metric = Metric(id="banking_npl_pct", label="NPL", value=25.0, unit="%",
                    as_of=date(2026, 1, 1), source="BB", cadence="quarterly")
    fired, level, rule_id = evaluate_risk_rules(_section("banking", [metric]))
    assert fired and level == "warning" and rule_id == "banking_npl_above_20"


def test_npl_15_does_not_fire():
    metric = Metric(id="banking_npl_pct", label="NPL", value=15.0, unit="%",
                    as_of=date(2026, 1, 1), source="BB", cadence="quarterly")
    fired, _, _ = evaluate_risk_rules(_section("banking", [metric]))
    assert not fired


def test_section_with_no_rules_returns_false():
    fired, _, _ = evaluate_risk_rules(_section("dse", []))
    assert not fired
