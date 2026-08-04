from brief.builders import SPINE_BUILDER_IDS, KEEP_BUILDER_IDS, ALL_BUILDER_IDS


def test_spine_ids_post_exclude():
    """nbr dropped from spine; dam remains excluded; comm retired in v1.6.7.
    Spine now has 10 sections."""
    assert SPINE_BUILDER_IDS == (
        "bb", "macro", "fx", "dse", "tbond", "iranwar",
        "headlines", "exec",
        "fiscal", "remit",
    )


def test_keep_ids_post_exclude():
    """Post-2026-05-03: only banking remains in KEEP."""
    assert KEEP_BUILDER_IDS == ("banking",)


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
