from brief.builders import SPINE_BUILDER_IDS, KEEP_BUILDER_IDS, ALL_BUILDER_IDS


def test_spine_ids_are_9():
    assert SPINE_BUILDER_IDS == (
        "bb", "macro", "fx", "remit", "dse", "tbond", "iranwar",
        "headlines", "exec",
    )


def test_keep_ids_are_5():
    assert KEEP_BUILDER_IDS == ("comm", "banking", "dam", "fiscal", "nbr")


def test_all_union_is_disjoint():
    assert set(SPINE_BUILDER_IDS).isdisjoint(KEEP_BUILDER_IDS)
    assert set(ALL_BUILDER_IDS) == set(SPINE_BUILDER_IDS) | set(KEEP_BUILDER_IDS)


def test_no_duplicate_ids():
    """Catches within-list duplicates (e.g. 'bb' appearing twice in SPINE)."""
    assert len(ALL_BUILDER_IDS) == len(set(ALL_BUILDER_IDS))

from datetime import date
from brief.builders import BuilderContext
from brief.econdelta import EconDeltaSnapshot
from datetime import datetime, timezone


def _empty_snap():
    return EconDeltaSnapshot(
        updated_at=datetime(2026, 4, 21, tzinfo=timezone.utc),
        sources_status={}, data={},
    )


def test_builder_context_holds_deps():
    ctx = BuilderContext(
        snapshot=_empty_snap(),
        history=None,
        today=date(2026, 4, 21),
        headlines=(),
        claude_outputs={},
    )
    assert ctx.today.year == 2026
    assert ctx.claude_outputs == {}
