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
