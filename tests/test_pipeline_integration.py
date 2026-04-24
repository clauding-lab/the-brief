import pytest

from brief.pipeline import gather, PipelineConfig
from brief.schema import SectionData


@pytest.mark.integration
def test_gather_returns_14_sections(fixture_snapshot, today):
    cfg = PipelineConfig(today=today, enable_history=False, enable_headlines=False)
    sections = gather(cfg, snapshot_override=fixture_snapshot)
    assert len(sections) == 14
    ids = [s.id for s in sections]
    assert ids == [
        "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
        "headlines", "exec",
        "comm", "banking", "dam", "fiscal", "nbr",
    ]
    for s in sections:
        assert isinstance(s, SectionData)
        assert s.freshness in ("fresh", "warning", "stale", "pending", "unavailable")
