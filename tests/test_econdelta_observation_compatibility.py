"""E1 additive producer metadata remains readable before B2 consumes it."""
import json
from pathlib import Path

from brief.econdelta import load_snapshot


def test_reader_accepts_old_and_observation_enriched_snapshots(tmp_path):
    old_path = Path(__file__).parent.parent / "fixtures" / "econdelta_latest.json"
    payload = json.loads(old_path.read_text())
    payload["observations"] = {
        "usd_bdt_mid": {"metric_id": "usd_bdt_mid", "value": payload["data"]["usd_bdt_mid"],
            "as_of": "2026-04-20", "unit": "BDT", "source": "bb_forex", "source_url": None,
            "captured_at": payload["updated_at"], "quality": "verified", "date_basis": "observation",
            "evidence": "Fixture's forex reading", "dependencies": [], "release_status": "unknown"}}
    enriched_path = tmp_path / "latest.json"
    enriched_path.write_text(json.dumps(payload))
    old, enriched = load_snapshot(old_path), load_snapshot(enriched_path)
    assert old.data == enriched.data
    assert old.updated_at == enriched.updated_at
    assert old.sources_status == enriched.sources_status
    assert old.get("usd_bdt_mid") == enriched.get("usd_bdt_mid")
