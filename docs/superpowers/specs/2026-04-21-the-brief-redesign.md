# The Brief — Architecture Redesign (2026-04-21)

**Status:** Approved design. Ready for implementation planning.
**Author:** Adnan Rashid (+ Claude Code brainstorming session)
**Scope:** Compute + content curation (scope B). Visual layout preserved.
**Replaces:** current monolithic Phase 2 HTML-regeneration pipeline in `update.py`.

## 1. Context and motivation

### Current state

The Brief's `update.py` generates the entire HTML document (`the-brief.html`, ~200KB) each morning via a single Claude call with `max_tokens=64000`. One Phase 1 call gathers data via web search; one Phase 2 call regenerates the HTML; one Phase 3 call regenerates 19 `BankerRead` insights in-place.

### Trigger

Today's run (#67) failed when the Anthropic API credit balance hit zero during Phase 2, truncating the output. The sanity guard caught it and preserved yesterday's HTML, but the failure exposed structural fragility:

1. A single large Claude call is all-or-nothing — any truncation kills the whole edition.
2. Claude is responsible for producing numeric facts, URLs, and layout — three distinct jobs, only one of which it's good at.
3. All sections refresh daily regardless of their underlying publication cadence.

### Product direction

The Brief is being grown into a standalone product — a morning Bangladesh-economy intelligence digest aimed at senior bankers (CFO, CRO, Head of SME Banking, Head of Corporate Banking, Treasury Head). Growing the subscriber base requires:

- **Fact discipline** — bankers will not tolerate invented numbers or misquoted rates.
- **Reliability** — daily ship without skipped days.
- **Cadence awareness** — monthly data labelled as monthly, not pretending to be daily.

### Top pains (ranked)

1. **A — Fact reliability.** Claude invents numbers and URLs.
2. **D — Run reliability.** Sanity guard trips, sections empty, day-to-day structure varies.
3. **F — Freshness/cadence.** Monthly data regenerates daily; no per-metric staleness.

All three resolve if Claude stops owning numeric facts.

### Compute migration constraint

Claude Max CLI caps single-call output at **32,000 tokens**. Current Phase 2 uses 64,000. The API has the 64k headroom, but pay-per-token economics do not scale for a product. Moving to Max requires decomposing Phase 2 regardless of architecture choice.

## 2. Design principles

1. **Claude never supplies a number or a URL it didn't receive as input.** All numeric facts flow through a typed `SectionData` contract populated by deterministic Python builders.
2. **Each section is an independent pipeline.** Gather → build contract → render. One section failing cannot block the rest.
3. **Cadence is a first-class type.** Every metric carries its own update frequency and age tolerance. Freshness is computed, not assumed.
4. **Python owns HTML.** Claude writes only small JSON narrative blobs that fill marked slots. Layout, CSS, JSX, chart rendering are fully deterministic.
5. **Every stage has a degradation path.** No single failure prevents the Brief from shipping.

## 3. Architecture

```
06:30 BDT (00:30 UTC)
     │
     ▼
┌────────────────────────────────┐
│ 1. GATHER (deterministic)      │
│   a. EconDelta latest.json     │
│   b. Supabase metric_history   │
│   c. Headlines scrape          │
│   d. Targeted news pulls       │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ 2. ASSEMBLE SectionData        │
│   12 spine + 8 optional        │
│   builders, one per section    │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ 3. NARRATIVE (Claude / Max)    │
│   3 small calls:               │
│   a. headlines_curation        │
│   b. exec_signals              │
│   c. bankerread_insights       │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ 4. RENDER (deterministic)      │
│   Python section templates +   │
│   placeholder splicing into    │
│   the-brief.html shell         │
└────────────┬───────────────────┘
             │
             ▼
┌────────────────────────────────┐
│ 5. PERSIST + DISTRIBUTE        │
│   Supabase history upsert,     │
│   git commit, Brevo email      │
└────────────────────────────────┘
```

### Repository layout

```
the-brief/
  brief/                      # New package
    __init__.py
    schema.py                 # Pydantic: Metric, SectionData, Delta, NewsItem, …
    cadence.py                # Cadence enum + freshness computation
    history.py                # Supabase metric_history read/write
    pipeline.py               # Orchestrator
    report.py                 # run_report.json + Discord notify
    builders/                 # One file per section
      __init__.py
      bb.py
      macro.py
      fx.py
      remittance.py
      dse.py
      tbond.py
      iranwar.py
      comm.py
      banking.py
      dam.py
      fiscal.py
      nbr.py
      headlines.py
      exec.py                 # Consumes other sections' output
    claude/
      __init__.py
      max_client.py           # subprocess wrapper around `claude -p`
      validators.py
      prompts/
        headlines_curation.txt
        exec_signals.txt
        bankerread.txt
        bankerread_stale.txt  # stale-section variant
    render/
      __init__.py
      assemble.py             # splice section fragments into index.html shell
      templates/              # one HTML/JSX fragment per section
        section_bb.html
        section_fx.html
        …
  update.py                   # Thin entrypoint; delegates to brief.pipeline
  ingest.py                   # Unchanged (Supabase upserts, no Anthropic deps)
  build.sh                    # Unchanged (JSX compile)
  the-brief.html              # Unchanged (visual template)
  docs/
    superpowers/specs/
      2026-04-21-the-brief-redesign.md  # This document
  deploy/
    brief.service
    brief.timer
    install.sh
    uninstall.sh
    logrotate.conf
```

## 4. Data contract

The `SectionData` Pydantic model is the spine of the system. Every spine builder produces one; every template consumes one.

```python
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel

CadenceKind = Literal["daily", "weekly", "monthly", "quarterly", "event"]
FreshnessKind = Literal["fresh", "warning", "stale", "pending", "unavailable"]
DirectionKind = Literal["up", "down", "flat"]
SignalKind = Literal["bull", "bear", "warn", "watch"]

class Delta(BaseModel):
    value: float
    direction: DirectionKind
    window: str  # "dod", "wow", "mom", "yoy"

class Metric(BaseModel):
    id: str
    label: str
    value: float | str | None
    unit: str
    as_of: date
    source: str
    source_url: str | None = None
    cadence: CadenceKind
    delta: Delta | None = None

class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published: datetime

class BankerReadInsight(BaseModel):
    sentences: list[str]  # exactly 4 on fresh path; 1 on stale path
    generated_at: datetime
    variant: Literal["full", "stale_micro"] = "full"

class ExecSignal(BaseModel):
    direction: SignalKind
    text: str             # ≤15 words
    section_anchor: str

class SectionData(BaseModel):
    id: str
    title: str
    metrics: list[Metric]
    news: list[NewsItem]
    freshness: FreshnessKind
    freshness_reason: str | None = None
    bankerread: BankerReadInsight | None = None
    exec_signals: list[ExecSignal] | None = None  # only SectionExec
```

### Section-level freshness is the worst metric-level freshness

```python
def section_freshness(metrics: list[Metric]) -> FreshnessKind:
    states = [metric_freshness(m) for m in metrics]
    for worst in ("unavailable", "stale", "pending", "warning"):
        if worst in states:
            return worst
    return "fresh"
```

### Example — concrete SectionData for SectionBB

```json
{
  "id": "bb",
  "title": "Policy & Rates (Bangladesh Bank)",
  "metrics": [
    {"id": "bb_policy_rate", "label": "Policy Rate", "value": 10.0, "unit": "%",
     "as_of": "2026-04-18", "source": "BB",
     "source_url": "https://www.bb.org.bd/",
     "cadence": "event",
     "delta": {"value": 0, "direction": "flat", "window": "mom"}},
    {"id": "sdf", "label": "SDF", "value": 8.5, "unit": "%", "as_of": "2026-04-18",
     "source": "BB", "cadence": "event", "delta": null},
    {"id": "gross_reserves", "label": "Gross Reserves", "value": 34.12, "unit": "bn USD",
     "as_of": "2026-04-20", "source": "BB", "cadence": "weekly",
     "delta": {"value": 0.3, "direction": "up", "window": "wow"}}
  ],
  "news": [],
  "freshness": "fresh",
  "freshness_reason": null,
  "bankerread": {
    "sentences": [
      "Policy rate held at 10% heading into the May MPC signals BB sees CPI risk outweighing growth risk.",
      "Action: stress-test the SME book's floating-rate exposure against another 50bp hike before May MPC.",
      "Watch for reserves breaking 34.5bn on remittance inflow; it loosens BB's FX intervention budget.",
      "Strategy: extend deposit tenor while rates are high; defer non-core corporate loan bookings."
    ],
    "generated_at": "2026-04-21T00:38:00Z",
    "variant": "full"
  },
  "exec_signals": null
}
```

## 5. Compute boundary — the three Claude calls

Claude runs exactly three calls per daily edition. Everything else is deterministic Python.

### Call 1 — `headlines_curation`

- **Output:** ~1,000 tokens JSON.
- **Tools:** none (`--tools ""`). No WebSearch, no WebFetch.
- **Input:** pre-scraped list of 12–30 headlines from DS, TBS, FE, Reuters, FT, BBC, Al Jazeera. Each item has `{title, url, source, published}`.
- **Claude's job:** rank and select 8–15 headlines, classify each by domain (banking, markets, fx, commodities, policy, geopolitics, headline-only). Cannot invent titles or URLs.
- **Output schema:**
  ```json
  {"selected": [{"url": "…", "domain": "fx", "weight": "high|med|low"}],
   "rationale_bullet": "one editorial sentence"}
  ```
- **Validator:** every selected `url` must exist in input set.
- **Fail-closed fallback:** display all scraped headlines as-is, no curation.

### Call 2 — `exec_signals`

- **Output:** ~2,000 tokens JSON.
- **Tools:** none.
- **Input:** every spine section's `SectionData` (metrics + freshness + deltas). Plus today's date. No raw HTML. No raw news text.
- **Claude's job:** produce 6–8 `{direction, text, section_anchor}` signals. Each `text` ≤15 words, must cite a specific metric + direction present in the input.
- **Output schema:**
  ```json
  {"signals": [{"direction": "bull|bear|warn|watch", "text": "…", "section_anchor": "bb"}],
   "traffic_status": "bull|bear|warn|neu"}
  ```
- **Validator:** every `section_anchor` is a real spine section id.
- **Fail-closed fallback:** reuse yesterday's `exec_signals` with a "(carried over)" stamp.

### Call 3 — `bankerread_insights`

- **Output:** ~8,000 tokens JSON.
- **Tools:** none.
- **Input:** all spine `SectionData` + today's `exec_signals` (from Call 2).
- **Claude's job:** one 4-sentence insight per spine section. Structure per section:
  1. What today's data means for the book.
  2. A named action with exposure type or threshold.
  3. A trigger to watch with metric + threshold.
  4. Strategic focus.
- **Stale-section variant:** for sections with `freshness != "fresh"`, Claude receives `bankerread_stale.txt` prompt variant instead. Output: one sentence news-driven micro-summary ("No fresh data; headlines suggest X.").
- **Output schema:**
  ```json
  {"insights": {"bb": ["s1","s2","s3","s4"], "fx": ["s1","s2","s3","s4"], …}}
  ```
- **Validator:** every key is a real section id; full variant has exactly 4 sentences; stale variant has exactly 1; no double quotes in any sentence (JSX breaking).
- **Fail-closed fallback:** per-section — if one section's insights malform, render that section's last edition's insights. Other sections ship normally.

### Token budget

| Call                  | Output | Quota impact                |
|-----------------------|--------|-----------------------------|
| `headlines_curation`  | ~1k    | minimal                     |
| `exec_signals`        | ~2k    | minimal                     |
| `bankerread_insights` | ~8k    | main driver                 |
| **Total output**      | **~11k** | Well under 32k per-call cap |

Input per call: ~15k tokens of `SectionData` JSON + prompt, plus 130k CLI scaffolding (first call creates cache, subsequent calls hit `cache_read` at ~10% cost).

### CLI invocation pattern

```python
subprocess.run([
    "claude", "-p", prompt_text,
    "--model", "claude-opus-4-7",
    "--output-format", "json",
    "--no-session-persistence",
    "--tools", "",
    "--permission-mode", "bypassPermissions",
], capture_output=True, text=True, timeout=1800)
```

Auth: Max OAuth via `~/.claude/.credentials.json` on VPS (same session used by the Discord bot).

## 6. Cadence, freshness, and failure behaviour

### Cadence taxonomy

| Cadence     | Fresh if                           | Warning if     | Stale if     |
|-------------|------------------------------------|----------------|--------------|
| `daily`     | ≤ 1 trading day old (see below)    | 1–2 trading days| > 2 trading days|
| `weekly`    | ≤ 7d                               | 7–10d          | > 10d        |
| `monthly`   | ≤ 35d from publication date        | 35–45d         | > 45d        |
| `quarterly` | ≤ 95d                              | 95–120d        | > 120d       |
| `event`     | Always fresh while active          | n/a            | until superseded |

BD trading days are Sun–Thu. A DSE close captured on Thursday afternoon remains `fresh` through Sat; the first `warning` state triggers only if Sunday's run fails to produce new data. Friday and Saturday runs deliberately skip the "daily" freshness check for markets-only metrics (DSE, T-bill cutoff yields).

### Freshness states

| State        | Visual                 | Numeric shown | Narrative behaviour                          |
|--------------|------------------------|---------------|----------------------------------------------|
| `fresh`      | no dot                 | yes           | full BankerRead                              |
| `warning`    | amber half-dot         | yes           | full BankerRead + "approaching stale" footer |
| `stale`      | amber solid dot        | last-known    | 1-sentence news-driven micro-summary         |
| `pending`    | blue pill "Next: …"    | last-known    | "Awaiting next publication" micro-line       |
| `unavailable`| grey "Data missing" card | none        | `SectionUnavailable` component               |

### Spine section → cadence mapping

| Section         | Dominant cadence            | Primary source                            |
|-----------------|-----------------------------|-------------------------------------------|
| BB              | `event` + `weekly`          | EconDelta + BB publications               |
| Macro (CPI/MPC) | `monthly`                   | BBS + BB MEI PDF                          |
| FX              | `daily` + `weekly`          | EconDelta `bb_forex`                      |
| Remittance      | `monthly`                   | BB `publictn/5/27`                        |
| DSE             | `daily`                     | EconDelta `dse_market`                    |
| T-Bond/Bill     | `event` + `daily`           | BB `monetaryactivity/treasury`            |
| Iran War / Oil  | `daily` + `event`           | EconDelta `commodity_prices` + news scrape|
| Banking         | `quarterly`                 | BB publication                            |
| Comm            | `daily` + `weekly`          | yfinance + Supabase                       |
| DAM             | `weekly`                    | DAM Bangladesh scrape                     |
| Fiscal / NBR    | `monthly`                   | MoF + news                                |
| Headlines       | `daily`                     | DS/TBS/FE/… scrape                        |
| Exec Signals    | `daily` (computed)          | Derived from all other sections           |

### Grace period

- `fresh → stale` requires **2 consecutive failed gathers** before flipping (prevents flicker from transient errors).
- `unavailable` only fires when Supabase `metric_history` has no last-known value.
- Reader never sees an empty section; minimum display is the stale or pending state.

### Last-known value store

Supabase table supporting last-known fallback + delta computation:

```sql
create table metric_history (
  metric_id text not null,
  as_of date not null,
  value jsonb not null,       -- flexible for scalars, arrays, objects
  source text not null,
  ingested_at timestamptz default now(),
  primary key (metric_id, as_of)
);
create index metric_history_lookup on metric_history (metric_id, as_of desc);
```

Every Brief run upserts fresh metric values; every builder reads the latest row for each of its metrics before computing freshness and deltas.

### Run report

Each run produces a `run_report.json`:

```json
{
  "run_id": "2026-04-21T00:30:00Z",
  "duration_sec": 1245,
  "section_freshness": {
    "bb": "fresh", "fx": "fresh", "cpi": "pending",
    "dse": "fresh", "tbond": "stale", "iranwar": "fresh"
  },
  "claude_calls": [
    {"name": "headlines_curation", "status": "ok", "ms": 12400, "tokens_out": 980},
    {"name": "exec_signals", "status": "ok", "ms": 18300, "tokens_out": 2100},
    {"name": "bankerread_insights", "status": "ok", "ms": 42100, "tokens_out": 8200}
  ],
  "fetch_failures": [],
  "html_bytes": 198432,
  "subscribers_emailed": 3
}
```

Discord alert triggers: any Claude call fails, any section goes `unavailable`, or total duration > 15 min. Discord stays quiet on fully clean runs.

## 7. Section inventory

Decision reference — ranked by Adnan in brainstorming:

**Spine (S — 13 sections + charts). Must ship daily; critical to product value.**

- SectionBB, SectionMacro, SectionFX, SectionRemittance
- SectionDSE, SectionTBond, SectionIranWar
- SectionExec, SectionHeadlines
- DSEXChart, TBillChart, OilChart, YieldCurveChart

**Keep (K — 8 sections). Useful, can degrade silently.**

- SectionBanking, SectionComm, SectionFiscal, SectionNBR
- SectionTariff, SectionTrade, SectionDAM
- LNGChart

**Cut (C — 3 sections). Remove from the-brief.html entirely.**

- SectionRMG
- SectionPower
- SectionPeers

Cuts land as part of Phase 4 (renderer). The existing React components stay in the repo as dead code initially; removal happens in a follow-up cleanup commit.

## 8. Migration sequence

Six incremental phases over ~6 days of elapsed time, ~17 hours of active work. Current GHA pipeline keeps running on API credits throughout; cutover happens after a 3-day shadow soak.

### Phase 1 — Scaffolding (day 1, ~3h)

- Create `brief/` package with `schema.py`, `cadence.py`, skeleton builders, empty templates.
- Add `pydantic>=2` to `requirements.txt`. Keep `anthropic` parallel path alive during migration.
- Unit-test schema + cadence with fixtures. No real data.

**Exit criteria:** `pytest` green; schema import works; `brief.cadence.section_freshness([])` returns `fresh`.

### Phase 2 — Builders (day 1–2, ~4h)

- Implement all 12 spine builders + 8 optional.
- Integrate EconDelta `latest.json` read via direct file read at `/home/adnan/econdelta/data/latest.json` (co-located on the same VPS; no HTTP needed).
- Supabase `metric_history` read/write.
- Headlines scraper ported from current `_scrape_headlines` verbatim.
- `builders/exec.py` and `builders/bankerread.py` stub out `bankerread=None`, `exec_signals=[]` — Claude wiring comes in Phase 3.

**Exit criteria:** running `brief.pipeline.gather()` on today's data produces valid `SectionData` for all 13 spine + 8 optional sections. Dumpable to JSON, validates.

### Phase 3 — Claude integration (day 2, ~3h)

- `claude/max_client.py` subprocess wrapper with timeout, retry, structured error handling.
- 3 prompt files + stale variant.
- 3 validators with fail-closed fallbacks.
- Wire into `builders/exec.py`, `builders/headlines.py`, `pipeline.py`.
- End-to-end dry-run on VPS (test user): gather → build → 3 Claude calls → JSON artifacts dumped, no render.

**Exit criteria:** 3 Claude calls succeed against real data, produce valid JSON, write to `artifacts/` dir for inspection.

### Phase 4 — Renderer (day 2–3, ~4h)

- Per-section HTML/JSX fragment templates (mirroring existing `the-brief.html` component shapes).
- `render/assemble.py` splices fragments + narrative slots into `index.html` shell.
- Cut sections (RMG/Power/Peers) removed from assemble output.
- Sanity check: output HTML passes existing `build.sh` without modification.

**Exit criteria:** full pipeline produces an `index.html` byte-comparable (within tolerance) to the current GHA output.

### Phase 5 — VPS deploy (day 3, ~2h)

- Clone to `~/brief/` on VPS, mirroring `~/econdelta/` layout.
- `/etc/brief.env`: `BREVO_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`, `FROM_EMAIL`, `DISCORD_WEBHOOK_URL`. **No `ANTHROPIC_API_KEY`.**
- Max OAuth via existing `~/.claude/.credentials.json` (same session the Discord bot uses).
- `deploy/brief.service` + `brief.timer`:
  ```
  OnCalendar=Sun..Fri 00:30 UTC
  MemoryMax=600M
  ProtectSystem=strict
  PrivateTmp=yes
  ```
- Git push-back: SSH deploy key for `clauding-lab/the-brief` with `contents: write`.
- `deploy/install.sh`, `uninstall.sh`, `logrotate.conf` — EconDelta pattern.

**Exit criteria:** `sudo systemctl start brief.service` produces a successful run, commit pushed to a shadow branch, Discord reports "clean".

### Phase 6 — Shadow soak and cutover (days 4–6, ~1h active)

- Shadow mode: VPS pipeline runs daily, writes to branch `shadow/new-pipeline-YYYY-MM-DD`, no push to main, no email.
- Each morning, diff shadow output vs. current GHA output; eyeball for regressions.
- A shadow run is **clean** iff `run_report.json` reports: all three Claude calls `status: ok`, `fetch_failures: []`, no section in `unavailable` state, and the rendered HTML passes `build.sh` without warnings.
- After **3 consecutive clean shadow runs**:
  - Disable GHA schedule (`schedule:` commented out in `daily-update.yml`; keep `workflow_dispatch` for emergencies).
  - Switch VPS pipeline to push to `main` + send email.
  - Monitor for 7 days.
- **Rollback path:** env flag `BRIEF_DRY_RUN=1` on VPS + re-enable GHA schedule. Both live in same repo; toggle in 2 minutes.

**Exit criteria:** 7 days of clean VPS runs with zero rollbacks. API cost drops to $0.

### Effort summary

| Phase                  | Day   | Effort | Risk                                    |
|------------------------|-------|--------|-----------------------------------------|
| 1 — Scaffolding        | 1     | 3h     | Low                                     |
| 2 — Builders           | 1–2   | 4h     | Low                                     |
| 3 — Claude integration | 2     | 3h     | Medium (new Max CLI territory)          |
| 4 — Renderer           | 2–3   | 4h     | Medium (template fidelity)              |
| 5 — VPS deploy         | 3     | 2h     | Low (EconDelta pattern proven)          |
| 6 — Shadow + cutover   | 4–6   | 1h     | Low                                     |
| **Total**              |       | **17h**|                                         |

## 9. Out of scope

Deliberately deferred from this migration:

- **EconDelta v2 scraper expansion.** The 48-indicator backlog from `econdelta/config/sources-v2.json` lands as a separate track. This migration uses whatever EconDelta currently provides + web-search fallback for the rest.
- **Visual redesign.** Existing layout stays. The `the-brief.html` JSX remains the visual template.
- **Rename to "The Debrief".** Declined.
- **Email-specific template.** Email continues using the same HTML as web (via `build.sh`).
- **Patch-JSON output format.** Renderer still emits full HTML files; a future optimization may shift to client-side diff/patch.
- **Dead-code removal of Cut sections.** React components stay in the repo initially; removal in a follow-up commit.
- **Intraday update capability.** Single daily run preserved. Event-driven re-runs (MPC decision, oil event) can land later as a separate workflow.

## 10. Success criteria

The migration is successful when all of the following hold for 7 consecutive calendar days post-cutover:

1. **Zero GHA runs.** The old `daily-update.yml` schedule is disabled; VPS is the sole producer.
2. **Zero Anthropic API spend.** All compute runs via Claude Max on VPS.
3. **Daily ship Sun–Fri.** The Brief produces a fresh `index.html` and sends subscriber emails every scheduled day.
4. **No fabricated facts.** Spot-checks of 10 random numeric values per day trace to their cited `source` + `as_of` date with zero discrepancies.
5. **Graceful degradation observed at least once.** At least one section enters `stale`, `pending`, or `unavailable` and renders correctly without blocking the rest.
6. **Run duration under 15 minutes.** Per the Discord alert threshold.
7. **Claude call validators pass 100%.** Fallback paths may trigger but the schema validators themselves never fail unexpectedly.
8. **Rollback rehearsed once.** Toggle `BRIEF_DRY_RUN=1`, re-enable GHA, verify old pipeline runs; then toggle back.

## 11. Environment variables

**VPS `/etc/brief.env` (chmod 640 root:adnan):**

```
BREVO_API_KEY=...
SUPABASE_URL=https://ssbliukchgibjcjohibi.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_SERVICE_KEY=...
FROM_EMAIL=adnan.rshd@gmail.com
DISCORD_WEBHOOK_URL=...
ECONDELTA_DATA=/home/adnan/econdelta/data/latest.json
BRIEF_DRY_RUN=0
```

**No `ANTHROPIC_API_KEY`.** Max OAuth via `/home/adnan/.claude/.credentials.json`.

## 12. References

- Current implementation: `update.py`, `ingest.py`, `build.sh` (this repo).
- EconDelta data contract: `~/Projects/clauding-lab/econdelta/data/latest.json`.
- EconDelta source expansion backlog: `~/Projects/clauding-lab/econdelta/config/sources-v2.json`.
- Original PRD conversation: see `brainstorming` session `2026-04-21` (not archived here).
- Trigger incident: GHA run #67 (2026-04-21 02:08 UTC) — credit-exhaustion truncation.
