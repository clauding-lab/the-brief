import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from brief.econdelta import EconDeltaSnapshot, load_snapshot, EconDeltaUnavailable, UNAVAILABLE_CAUSES

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


def test_malformed_updated_at_raises_unavailable(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"updated_at": 12345, "sources_status": {}, "data": {}}')
    with pytest.raises(EconDeltaUnavailable):
        load_snapshot(bad)


def test_source_status():
    snap = load_snapshot(FIXTURE)
    assert snap.source_status("bb_forex") == "ok"
    assert snap.source_status("dse_market") == "ok"
    assert snap.source_status("does_not_exist") is None


# ── Standing-rate writer confirmations (policy corridor only) ────────────────
CONFIRM_TODAY = date(2026, 9, 25)
CORRIDOR_IDS = ("policy_rate_repo", "policy_rate_sdf", "policy_rate_slf")


def _confirmation(mid: str = "policy_rate_repo", **changes) -> dict:
    return {"metric_id": mid, "value": 9.5, "as_of": "2026-09-24", "unit": "%",
            "source": mid, "source_url": None, "captured_at": "2026-09-24T19:45:00+00:00",
            "quality": "verified", "date_basis": "writer_confirmation",
            "evidence": "html_labeled_value", "dependencies": [],
            "release_status": "unknown", **changes}


def _snap(mid: str, item: dict, value: object = 9.5) -> EconDeltaSnapshot:
    return EconDeltaSnapshot(updated_at=datetime(2026, 9, 24, 20, 56, tzinfo=timezone.utc),
                             sources_status={}, data={mid: value}, observations={mid: item})


@pytest.mark.parametrize("mid", CORRIDOR_IDS)
def test_corridor_confirmation_is_liveness_evidence_never_an_observation(mid):
    snap = _snap(mid, _confirmation(mid))
    confirmation = snap.writer_confirmation(mid, today=CONFIRM_TODAY)
    assert confirmation is not None
    assert (confirmation.metric_id, confirmation.value, confirmation.confirmed_on,
            confirmation.quality) == (mid, 9.5, date(2026, 9, 24), "verified")
    # The dated-observation path still refuses it: a confirmation date is not
    # the date a rate was observed or decided.
    assert snap.observation(mid, today=CONFIRM_TODAY) is None


def test_restamped_quote_outside_the_corridor_is_not_a_confirmation():
    mid = "brent_crude_usd_barrel"
    snap = _snap(mid, _confirmation(mid, value=80, unit="USD/barrel"), value=80)
    assert snap.writer_confirmation(mid, today=CONFIRM_TODAY) is None
    assert snap.observation(mid, today=CONFIRM_TODAY) is None


@pytest.mark.parametrize("changes", [
    {"metric_id": "policy_rate_sdf"},
    {"value": 9.25},
    {"value": float("nan")},
    {"value": True},
    {"quality": "unavailable"},
    {"date_basis": "observation"},
    {"date_basis": "unknown"},
    {"source": ""},
    {"source": None},
    {"evidence": "  "},
    {"evidence": None},
    {"captured_at": "2026-09-24T19:45:00"},
    {"captured_at": "not a time"},
    {"captured_at": None},
    {"as_of": "2026-09-25"},
    {"as_of": "2026-09-26", "captured_at": "2026-09-26T01:00:00+00:00"},
    {"as_of": None},
    {"as_of": "24 Sep 2026"},
], ids=["wrong-metric-id", "value-differs-from-data", "nan", "bool", "unavailable",
        "observation-basis", "unknown-basis", "blank-source", "missing-source",
        "blank-evidence", "missing-evidence", "naive-capture", "unparseable-capture",
        "missing-capture", "after-capture-date", "after-today", "undated", "unparseable-date"])
def test_corridor_confirmation_failing_integrity_is_rejected(changes):
    snap = _snap("policy_rate_repo", _confirmation(**changes))
    assert snap.writer_confirmation("policy_rate_repo", today=CONFIRM_TODAY) is None


# ── Snapshot envelope: a malformed file is unavailable, never a healthy default ──
LEGACY_ENVELOPE = {"updated_at": "2026-09-24T20:56:00Z", "sources_status": {}, "data": {"usd_bdt_mid": 122.7}}


def _write(tmp_path, payload) -> Path:
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload))
    return path


def _unavailable_reason(path) -> str:
    with pytest.raises(EconDeltaUnavailable) as caught:
        load_snapshot(path)
    return str(caught.value)


@pytest.mark.parametrize("payload", [[LEGACY_ENVELOPE], "latest", 42, None],
                         ids=["list", "string", "number", "null"])
def test_a_snapshot_whose_top_level_is_not_an_object_is_unavailable(tmp_path, payload):
    assert "not an object" in _unavailable_reason(_write(tmp_path, payload))


@pytest.mark.parametrize("stamp", ["2026-09-24T20:56:00", "2026-09-24"], ids=["naive", "date-only"])
def test_a_capture_time_without_a_timezone_is_unavailable(tmp_path, stamp):
    # A naive instant cannot be placed on the UTC timeline: its age is unknown.
    reason = _unavailable_reason(_write(tmp_path, {**LEGACY_ENVELOPE, "updated_at": stamp}))
    assert "updated_at" in reason and "timezone" in reason


@pytest.mark.parametrize("stamp", [None, ["2026-09-24T20:56:00Z"], "yesterday"],
                         ids=["null", "list", "unparseable"])
def test_a_non_iso_capture_time_is_unavailable(tmp_path, stamp):
    assert "updated_at" in _unavailable_reason(_write(tmp_path, {**LEGACY_ENVELOPE, "updated_at": stamp}))


@pytest.mark.parametrize("field", ["updated_at", "sources_status", "data"])
def test_every_producer_version_writes_the_core_envelope_so_absence_is_unavailable(tmp_path, field):
    # EconDelta's LatestBundle has required these since the legacy v1 shape; an empty
    # default would read as "no upstream problems" / "no readings" without evidence.
    payload = {k: v for k, v in LEGACY_ENVELOPE.items() if k != field}
    assert field in _unavailable_reason(_write(tmp_path, payload))


@pytest.mark.parametrize("field,value", [
    ("sources_status", []), ("sources_status", None), ("sources_status", "ok"),
    ("data", []), ("data", None), ("data", 122.7),
    ("observations", []), ("observations", None), ("observations", "records"),
])
def test_a_wrongly_typed_envelope_field_is_unavailable_not_silently_emptied(tmp_path, field, value):
    reason = _unavailable_reason(_write(tmp_path, {**LEGACY_ENVELOPE, field: value}))
    assert field in reason and "not an object" in reason


@pytest.mark.parametrize("write_status", [[], "ok", 1, True], ids=["list", "string", "number", "bool"])
def test_a_present_but_malformed_receipt_block_loads_as_found_so_readiness_holds_on_it(tmp_path, write_status):
    # Malformed receipt -> hold (contradiction). Rejecting the whole file here would turn it
    # into "unavailable" -> degraded, and the publish would go ahead on a contradicted receipt.
    snap = load_snapshot(_write(tmp_path, {**LEGACY_ENVELOPE, "write_status": write_status}))
    assert snap.write_status == write_status and type(snap.write_status) is type(write_status)
    assert snap.load_error is None and snap.data == {"usd_bdt_mid": 122.7}


@pytest.mark.parametrize("extra", [{}, {"write_status": None}], ids=["absent", "null"])
def test_a_legacy_snapshot_without_receipts_or_observations_still_loads_with_no_receipt(tmp_path, extra):
    # Pre-receipt producers omit write_status (or serialise LatestBundle's None default);
    # pre-E1 producers omit observations. Absence stays absence: no invented write.
    snap = load_snapshot(_write(tmp_path, {**LEGACY_ENVELOPE, **extra}))
    assert snap.write_status is None and snap.observations == {}
    assert snap.data == {"usd_bdt_mid": 122.7}


def test_a_truncated_snapshot_is_unavailable(tmp_path):
    whole = FIXTURE.read_bytes()
    path = tmp_path / "latest.json"
    path.write_bytes(whole[: len(whole) // 2])
    assert "unparseable" in _unavailable_reason(path)


def test_a_snapshot_with_corrupt_bytes_is_unavailable(tmp_path):
    path = tmp_path / "latest.json"
    path.write_bytes(b'{"updated_at": "\xff\xfe')
    assert "unparseable" in _unavailable_reason(path)


def test_a_snapshot_path_that_cannot_be_read_as_a_file_is_unavailable(tmp_path):
    assert "unreadable" in _unavailable_reason(tmp_path)  # a directory, not a file


@pytest.mark.parametrize("entry", [None, "ok", ["ok"]], ids=["null", "string", "list"])
def test_source_status_helpers_treat_a_malformed_entry_as_unknown(entry):
    snap = EconDeltaSnapshot(updated_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
                             sources_status={"cpi": entry}, data={})
    assert snap.source_status("cpi") is None
    assert snap.source_age_hours("cpi") is None


# ── Owner decision (e): each unusable file carries ONE fixed cause category for the operator
# alert. The category is chosen from the failure itself, never copied from error text. ──
_BENGALI = '{"note": "ঢাকা"}'.encode()


@pytest.mark.parametrize("raw,cause", [
    (b"", "truncated"),                                                   # interrupted copy: nothing
    (b'{"updated_at": "2026-09-24T20:56:00Z", "sources_status": {}, "da', "truncated"),  # cut in a string
    (b'{"updated_at": "2026-09-24T20:56:00Z", "data": {"x": 1', "truncated"),  # cut after a value
    (_BENGALI[:12], "truncated"),                                         # cut inside a UTF-8 character
    (b"<html>502 Bad Gateway</html>", "unparseable"),                     # not JSON at all
    (b'{"a": 1} {"a": 2}', "unparseable"),                                # complete, then extra data
    (b'{"a": 1,}', "unparseable"),                                        # complete length, bad syntax
    (b"\xff\xfe{}", "unparseable"),                                       # corrupt bytes up front
], ids=["empty", "cut-in-string", "cut-after-value", "cut-in-utf8-char", "html", "extra-data",
        "trailing-comma", "corrupt-bytes"])
def test_an_undecodable_snapshot_is_classified_truncated_only_when_it_ends_early(tmp_path, raw, cause):
    path = tmp_path / "latest.json"
    path.write_bytes(raw)
    with pytest.raises(EconDeltaUnavailable) as err:
        load_snapshot(path)
    assert err.value.cause == cause


def test_each_unusable_snapshot_names_its_cause_category(tmp_path):
    directory = tmp_path / "dir.json"
    directory.mkdir()
    wrong_shape = tmp_path / "list.json"
    wrong_shape.write_text("[]")
    causes = {}
    for label, path in (("missing", tmp_path / "absent.json"), ("unreadable", directory),
                        ("wrong shape", wrong_shape)):
        with pytest.raises(EconDeltaUnavailable) as err:
            load_snapshot(path)
        causes[label] = err.value.cause
    assert causes == {"missing": "missing", "unreadable": "unreadable", "wrong shape": "wrong shape"}
    assert set(causes.values()) <= set(UNAVAILABLE_CAUSES)
