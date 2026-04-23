import json
from datetime import date
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot, load_snapshot, EconDeltaUnavailable

FIXTURE = Path(__file__).parent.parent / "fixtures" / "econdelta_latest.json"


def test_load_snapshot_from_fixture():
    snap = load_snapshot(FIXTURE)
    assert isinstance(snap, EconDeltaSnapshot)
    assert snap.data["usd_bdt_mid"] == 122.70
    assert snap.sources_status["bb_forex"]["status"] == "ok"
    assert snap.updated_at.year == 2026


def test_get_helper_returns_none_for_missing_key():
    snap = load_snapshot(FIXTURE)
    assert snap.get("nope_key") is None
    assert snap.get("usd_bdt_mid") == 122.70


def test_source_age_hours():
    snap = load_snapshot(FIXTURE)
    assert snap.source_age_hours("bb_forex") == 0.08
    assert snap.source_age_hours("does_not_exist") is None


def test_missing_file_raises_unavailable(tmp_path):
    with pytest.raises(EconDeltaUnavailable):
        load_snapshot(tmp_path / "missing.json")


def test_bad_json_raises_unavailable(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid")
    with pytest.raises(EconDeltaUnavailable):
        load_snapshot(bad)
