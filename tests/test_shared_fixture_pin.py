"""The shared producer/consumer contract fixture cannot drift between the two repos.

tests/fixtures/contracts/brief-observations-v1.json lives, byte-identical, in both The Brief
and EconDelta: EconDelta proves its producer makes exactly these records, The Brief proves its
builders, readiness check and publish sequence accept exactly these records. CI checks out one
repo at a time, so neither side can compare against the other copy directly. Instead both repos
pin the SAME SHA-256 here (this file is identical in both repos). Changing the fixture means
changing both copies and this constant in both repos in the same change; editing only one side
fails that side's CI instead of letting the two contracts silently diverge.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

SHARED_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "contracts" / "brief-observations-v1.json"

# Agreed version of the shared fixture (both copies, 28 Sep 2026). Update in BOTH repos together.
SHARED_FIXTURE_SHA256 = "ce2654eec5c83c6bdfa517c62982b4319c6f3d2032807bb2479dbe4a0890fd1d"


def test_shared_contract_fixture_is_the_version_both_repos_agreed() -> None:
    actual = hashlib.sha256(SHARED_FIXTURE.read_bytes()).hexdigest()
    assert actual == SHARED_FIXTURE_SHA256, (
        f"{SHARED_FIXTURE.name} changed on this side only (sha256 {actual}). Copy the same bytes "
        "to the other repo and update SHARED_FIXTURE_SHA256 in tests/test_shared_fixture_pin.py "
        "in BOTH repos in the same change."
    )
