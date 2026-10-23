"""EconDelta's CPI/M2 upstream source-poll liveness entries from the shared contract (R2 fix 5).

Readiness requires both entries: a snapshot without them has unknown CPI/M2 liveness and
degrades. A test that means "a fully healthy current producer" therefore carries
POLLED_UPSTREAM in its sources_status.
"""
import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).parent / "fixtures/contracts/brief-observations-v1.json")
                      .read_text())["upstream_liveness_contract"]
POLLED_UPSTREAM: dict[str, dict] = CONTRACT["polled_upstream_jobs"]["sources_status"]
STOPPED_UPSTREAM: dict[str, dict] = CONTRACT["stopped_upstream_jobs"]["sources_status"]
# R2 fix H3: what the producer publishes after its daily fetch polled every CPI/M2 page live.
LIVE_UPSTREAM: dict[str, dict] = CONTRACT["live_upstream_polls"]["sources_status"]
