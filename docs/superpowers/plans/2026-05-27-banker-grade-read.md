# Banker-Grade Read v1.4.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v1.4.0 "Banker-Grade Read" — adds historical-anchor compute, banker-grade prompt + sub-editor specificity enforcement, abbreviation tier policy, macro section enrichment with 8 monthly metrics + CPI trend chart, and `chart_read` interpretive layer beneath every chart card. Closes the depth gap surfaced in the 2026-05-27 brainstorm.

**Architecture:** Pipeline + prompt + minimal-UI changes. Six phases (0-5) mapping to ~5 PRs. Phase 0 is investigation-only (no code shipped) — verifies Anthropic SDK web_search support, captures baseline open-rate, spot-checks `metric_history_monthly` data quality, decides React testing infra. Phases 1+2 run in parallel (independent files). Phase 3 requires both. Phase 4 requires Phase 3. Phase 5 is the release loop.

**Tech Stack:** Python 3.x + pytest (pipeline), Next.js 16 + TypeScript + Chart.js 4 (SPA), Supabase (data), Anthropic SDK via `brief/claude/max_client.py`. Source spec: [`docs/superpowers/specs/2026-05-27-banker-grade-read-design.md`](../specs/2026-05-27-banker-grade-read-design.md).

**Estimated session length:** ~8-12 hours total across all 5 PRs. Each PR ~1.5-3 hours of work assuming clean execution.

---

## Files Inventory

| File | Phase | Action | Lines of impact (est.) | Responsibility |
|---|---|---|---|---|
| `brief/history_anchors.py` | 1 | **CREATE** | ~250 | 5 compute primitives + HistoryFact dataclass + cadence routing |
| `brief/history.py` | 1 | MODIFY | ~30 | Add `metric_history_monthly` read path (new client or extended) |
| `tests/test_history_anchors.py` | 1 | **CREATE** | ~350 | Unit tests for 5 primitives + cadence routing + gap robustness |
| `brief/claude/validators.py` | 2 | MODIFY | ~150 | Add 6 validators + 6 module constants |
| `tests/test_claude_validators.py` | 2 | **CREATE** | ~250 | Unit tests for 6 new validators |
| `brief/claude/prompts/subeditor_v6.txt` | 2 | MODIFY | ~80 | 7 new checklist items |
| `Master.md` | 2 | MODIFY | ~50 | Add "Banker vocabulary tiers" subsection |
| `brief/claude/max_client.py` | 0 | INVESTIGATE | 0 | Verify web_search tool support; outcome decides Phase 2 scope |
| `brief/claude/prompts/editor_v6.txt` | 3 | MODIFY | ~80 | Specificity rubric, field constraints, history_facts weaving, abbreviation policy, macro override |
| `brief/claude/prompts/editor_v6_friday.txt` | 3 | MODIFY | ~80 | Same updates as editor_v6.txt |
| `brief/builders/macro.py` | 3 | **REWRITE** | ~100 | Read 8 monthly metrics from `metric_history_monthly` + produce history_facts |
| `brief/pipeline_v6.py` | 3 | MODIFY | ~30 | Wire history_facts through BuilderContext into editor input |
| `brief/schema.py` | 3 | MODIFY | ~10 | Add `history_facts` field to SectionData dataclass |
| `lib/chartConfigs.ts` | 3 | MODIFY | ~80 | Add `cpiTrend` config + SECTION_TO_CHART entry |
| `tests/test_pipeline_v6_macro_enrichment.py` | 3 | **CREATE** | ~150 | Integration test for macro reading metric_history_monthly + history_facts |
| `types/brief.ts` | 4 | MODIFY | ~15 | Add `ChartRead` interface + `Section.chart_read` field |
| `app/components/Section.tsx` | 4 | MODIFY | ~10 | Render chart_read paragraphs under BriefChart |
| `brief/v6_schema.py` | 4 | MODIFY | ~15 | Add chart_read JSON schema for editor output validation |
| `tests/test_pipeline_v6_chart_read.py` | 4 | **CREATE** | ~120 | Integration test for chart_read population + schema validation |
| `CHANGELOG.md` | 5 | MODIFY | ~40 | v1.4.0 entry |
| `package.json` | 5 | MODIFY | 1 | Bump 1.3.2 → 1.4.0 |
| `README.md` | 5 | MODIFY | 2 | Bump version badge + footer |
| `AGENT_LEARNINGS.md` | 5 | MODIFY | ~25 | Append v1.4.0 release entry post-ship |

---

## Preview-before-prod governance (applies to every phase)

**Adnan's hard rule:** every change must be live-tested on a separate URL before merging to main or replacing the live site. Subagent workflow MUST end each phase PR with a "PREVIEW READY — please review at <URL>" nudge and wait for explicit user approval before merging.

| Change type | Preview path |
|---|---|
| SPA-only (Phase 4) | Vercel auto-deploys a preview URL per PR. Eyeball the preview deploy. |
| Editorial pipeline (Phase 3) | Use the fixture-loading mechanism built in Phase 0.5. Dry-run pipeline locally → commit JSON fixture → Vercel preview SPA renders v1.4.0 brief content. |
| Pure backend (Phases 1, 2) | No visual preview applicable; verify via local pytest + dry-run pipeline JSON inspection. Adnan-visible artifact: the dry-run JSON file path. |

**Nudge protocol per phase:**
1. Subagent completes all tasks in a phase.
2. Subagent pushes PR + waits for Vercel preview URL to be ready.
3. Orchestrator (this session) summarizes to Adnan with the preview URL.
4. Adnan reviews preview, replies "merge" / "needs changes" / "reject".
5. Only then is the phase PR merged.

## Phase 0 — Pre-flight verifications (no code shipped, 4 tasks)

> **PR boundary:** Phase 0 is investigation-only. Findings are recorded in this plan via task completion notes; no commits go to a feature branch. If Phase 0 surfaces blockers (e.g., web_search unsupported), revise Phase 2 scope BEFORE starting Phase 2.

### Task 0.1: Verify Anthropic SDK web_search tool support

**Files:** read `brief/claude/max_client.py`, `requirements.txt`, `requirements-dev.txt`

- [ ] **Step 1:** Read `brief/claude/max_client.py` to determine which Anthropic SDK version is in use and whether tool-use is invoked anywhere.

```bash
grep -n "tools\|tool_use\|web_search\|client.messages" brief/claude/max_client.py
grep -E "anthropic" requirements.txt requirements-dev.txt
```

- [ ] **Step 2:** Check the installed Anthropic SDK version.

```bash
.venv/bin/pip show anthropic | grep Version
```

- [ ] **Step 3:** Determine auth mode. The brief currently uses Claude Code OAuth (per AGENT_LEARNINGS.md May 9 entry — `~/.claude/.credentials.json`). The `web_search` server-side tool requires direct API key auth OR an SDK version that supports tool-use over OAuth.

Test in a throwaway Python script:

```python
# /tmp/verify_web_search.py
import os
from anthropic import Anthropic

client = Anthropic()  # uses default auth chain
try:
    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=200,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": "Search: current Bangladesh Bank policy rate"}],
    )
    print("OK:", resp.stop_reason)
except Exception as e:
    print("FAIL:", type(e).__name__, e)
```

Run: `.venv/bin/python /tmp/verify_web_search.py`

- [ ] **Step 4:** Record outcome in this task (edit plan inline) — one of:
  - **GREEN** — web_search returns a result. Phase 2 ships sub-editor check #5 as designed.
  - **YELLOW** — web_search works but auth needs `ANTHROPIC_API_KEY` env var. Phase 2 adds a config switch + docs.
  - **RED** — web_search not supported in current SDK/auth. **Edit the v1.4.0 spec at `docs/superpowers/specs/2026-05-27-banker-grade-read-design.md` to mark §3.4 check #5 as deferred to v1.4.x.** Update Phase 2 below to skip the web_search wiring task.

- [ ] **Step 5:** No commit (investigation-only).

### Task 0.2: Capture pre-v1.4.0 email open-rate baseline

**Files:** none (out-of-band data capture)

- [ ] **Step 1:** Query Brevo's API for the last 14 days of campaign opens for the brief's transactional template (the daily email). Or — if the brief doesn't track opens via Brevo's stats, capture whatever proxy exists (subscriber count growth as a fallback indicator).

Example Brevo API call:

```bash
curl -s -H "api-key: $BREVO_API_KEY" \
  "https://api.brevo.com/v3/transactionalEmails/statistics/events?days=14&template_id=<TEMPLATE_ID>" \
  | jq '.events | group_by(.event) | map({event: .[0].event, count: length})'
```

- [ ] **Step 2:** Record the open rate (and supporting numbers) in the success-criteria comparison spreadsheet (or — if no spreadsheet exists — in a comment in `docs/superpowers/specs/2026-05-27-banker-grade-read-design.md` under §5 Success criteria).

- [ ] **Step 3:** No commit (data capture only).

### Task 0.3: Spot-check `metric_history_monthly` data quality

**Files:** none (Supabase Studio queries)

- [ ] **Step 1:** Pick 3 monthly series — recommend `cpi_12m_avg_monthly`, `real_policy_rate_monthly`, `reer_monthly`.

- [ ] **Step 2:** Query the last 12 months of each via Supabase Studio:

```sql
SELECT metric_id, as_of, value, source
FROM metric_history_monthly
WHERE metric_id = 'cpi_12m_avg_monthly'
ORDER BY as_of DESC
LIMIT 12;
```

- [ ] **Step 3:** Cross-check each series' most recent and most extreme rows against the source authority:
  - `cpi_12m_avg_monthly` → BBS monthly CPI release
  - `real_policy_rate_monthly` → BB repo rate − P-to-P CPI (computed; verify formula)
  - `reer_monthly` → BB FX reserves & REER bulletin

- [ ] **Step 4:** Record findings. If any series shows discrepancy >25% on the latest row (matching the same materiality threshold from §3.4 web search check), pause v1.4.0 and ask Adnan whether to fix EconDelta backfill first or proceed with caveats.

- [ ] **Step 5:** No commit.

### Task 0.4: Decide React component testing infrastructure

**Files:** read `package.json`, `tsconfig.json`, search for any existing test runner config

- [ ] **Step 1:** Search the repo for any React testing infrastructure that may exist.

```bash
ls app/components/__tests__ 2>/dev/null
grep -E "vitest|jest|@testing-library" package.json
find . -name "vitest.config.*" -not -path "./node_modules/*" -not -path "./.next/*" 2>/dev/null
```

- [ ] **Step 2:** Two outcomes:
  - **EXISTS:** record the test command (e.g., `npm run test:unit`) — Task 4.5 uses it.
  - **NOT EXISTS:** Decide between (a) adding Vitest + React Testing Library in Phase 4 as a separate task, OR (b) skipping component tests in v1.4.0 and relying on Vercel preview visual eyeballing.

  **Default recommendation:** (b) skip for v1.4.0. The ChartRead render is structurally trivial (3 div lines, 1 conditional) and is visually verifiable on Vercel preview. Adding a test infra is its own decision worth more deliberation than v1.4.0 should bear.

- [ ] **Step 3:** Record the decision in plan task 4.5 below.

- [ ] **Step 4:** No commit.

---

## Phase 0.5 — Preview fixture infrastructure (3 tasks, 1 PR)

> **PR boundary:** Phase 0.5 ships as a small standalone PR titled `feat(spa): /preview route with fixture-loading for pre-prod review`. Permanent infrastructure — used by v1.4.0 and every future release. ~50-80 LOC.

> Before starting: `git switch main && git pull --ff-only && git switch -c feat/spa-preview-fixture-route`

### Task 0.5.1: Add `/preview` route that loads brief from a fixture JSON path

**Files:**
- Create: `app/preview/page.tsx`
- Modify: `app/components/ClientApp.tsx` (if needed — to skip Supabase fetch when fixture mode)
- Create: `public/fixtures/.gitkeep` (placeholder, fixture JSONs land here)

- [ ] **Step 1: Read current ClientApp / page entry point** to understand the brief loading path.

```bash
grep -n "get_latest_brief\|supabase\.rpc\|useEffect" app/components/ClientApp.tsx app/page.tsx
```

- [ ] **Step 2: Create `app/preview/page.tsx`** — server component that reads the `?fixture=<filename>` query param and loads JSON from `public/fixtures/<filename>`:

```tsx
// app/preview/page.tsx
import { notFound } from "next/navigation";
import fs from "node:fs/promises";
import path from "node:path";

import { ClientApp } from "@/app/components/ClientApp";
import type { BriefPayload } from "@/types/brief";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ fixture?: string }>;
}

export default async function PreviewPage({ searchParams }: PageProps) {
  const { fixture } = await searchParams;
  if (!fixture) {
    return (
      <main style={{ padding: "2rem", fontFamily: "var(--mono, monospace)" }}>
        <h1>Preview mode</h1>
        <p>
          Append <code>?fixture=&lt;filename&gt;</code> to load a brief JSON from
          <code>public/fixtures/</code>.
        </p>
        <p>
          Example: <code>/preview?fixture=v1.4.0-dryrun-2026-05-28.json</code>
        </p>
      </main>
    );
  }

  // Allowlist filename — only .json files, no path traversal
  if (!/^[a-zA-Z0-9._-]+\.json$/.test(fixture)) {
    return notFound();
  }

  const fixturePath = path.join(process.cwd(), "public", "fixtures", fixture);
  let raw: string;
  try {
    raw = await fs.readFile(fixturePath, "utf-8");
  } catch {
    return notFound();
  }

  let payload: BriefPayload;
  try {
    payload = JSON.parse(raw) as BriefPayload;
  } catch {
    return notFound();
  }

  return <ClientApp brief={payload.brief} sections={payload.sections} preview />;
}
```

- [ ] **Step 3: Add `preview?: boolean` prop to ClientApp** — when true, render a small "PREVIEW MODE" indicator and skip any Supabase polling:

```tsx
// app/components/ClientApp.tsx — add to props interface and render
interface ClientAppProps {
  brief?: Brief;
  sections: Section[];
  preview?: boolean;  // NEW
}

export function ClientApp({ brief, sections, preview = false }: ClientAppProps) {
  // ... existing logic ...
  return (
    <>
      {preview && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0,
          background: "var(--tone-warn)", color: "var(--ink-1)",
          padding: "4px 12px", fontFamily: "var(--mono)", fontSize: 12,
          textAlign: "center", zIndex: 1000,
        }}>
          PREVIEW MODE · fixture-loaded · NOT live data
        </div>
      )}
      {/* existing render */}
    </>
  );
}
```

- [ ] **Step 4: Create the fixtures directory** with a placeholder:

```bash
mkdir -p public/fixtures
touch public/fixtures/.gitkeep
```

- [ ] **Step 5: Type-check + lint**

```bash
npx tsc --noEmit
npm run lint
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/preview/page.tsx app/components/ClientApp.tsx public/fixtures/.gitkeep
git commit -m "feat(spa): /preview route with fixture-loading for pre-prod review

Adds app/preview/page.tsx — server component reading ?fixture=<name>
query param, loading JSON from public/fixtures/<name>, rendering via
ClientApp with a 'PREVIEW MODE' banner.

Permanent infra for the preview-before-prod governance rule. Used by
v1.4.0 (and every future release) to let Adnan eyeball editorial
content changes on a Vercel preview URL before they go live."
```

### Task 0.5.2: Add CLI flag to write dry-run output to a fixture file

**Files:**
- Modify: `brief/cli.py` — add `--write-fixture=<filename>` flag
- Modify: `tests/test_cli.py` (extend existing)

- [ ] **Step 1: Write the failing test**

```python
def test_cli_writes_fixture_on_dry_run(tmp_path, monkeypatch):
    fixture_path = tmp_path / "test-fixture.json"
    # ... set up mock pipeline output ...
    args = [
        "run", "--publish", "--dry-run", "--no-notify",
        f"--write-fixture={fixture_path}",
    ]
    exit_code = main(args)
    assert exit_code == 3  # dry-run-ok
    assert fixture_path.exists()
    payload = json.loads(fixture_path.read_text())
    assert "brief" in payload
    assert "sections" in payload
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Extend `brief/cli.py`** — add `--write-fixture` argparse flag; on dry-run, serialize the editor's output to the path:

```python
# In _parse():
r.add_argument(
    "--write-fixture",
    type=str,
    default=None,
    help="When set, write the dry-run output JSON to this path (for SPA preview)",
)

# In run():
if args.write_fixture and args.dry_run:
    fixture_path = Path(args.write_fixture)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(payload, indent=2, default=str))
    logger.info("Wrote dry-run fixture: %s", fixture_path)
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/cli.py tests/test_cli.py
git commit -m "feat(cli): add --write-fixture flag for SPA preview workflow

CLI usage: python -m brief.cli run --publish --dry-run --no-notify
  --write-fixture=public/fixtures/v1.4.0-dryrun-YYYY-MM-DD.json

Then load on preview URL: <preview-url>/preview?fixture=v1.4.0-dryrun-YYYY-MM-DD.json"
```

### Task 0.5.3: Push Phase 0.5 PR and verify preview URL works

**Files:** none

- [ ] **Step 1: Push**

```bash
git push -u origin feat/spa-preview-fixture-route
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --head feat/spa-preview-fixture-route \
  --title "feat(spa): /preview route with fixture-loading for pre-prod review" \
  --body "Permanent infrastructure for the preview-before-prod governance rule.

## What it does

- Adds /preview route at app/preview/page.tsx — server component reading ?fixture=<name>
  query param, loading JSON from public/fixtures/<name>, rendering via ClientApp with
  a yellow 'PREVIEW MODE' banner.
- Adds --write-fixture flag to brief/cli.py — pipeline dry-runs write directly to a
  fixture file ready for SPA loading.

## Workflow this enables

1. Run pipeline locally: python -m brief.cli run --publish --dry-run --no-notify --write-fixture=public/fixtures/<release>-<date>.json
2. Commit fixture JSON to the feature branch
3. Vercel auto-deploys preview
4. Load <preview-url>/preview?fixture=<release>-<date>.json
5. Eyeball editorial content on a real browser hitting a real URL before approving merge

## Test plan
- [x] /preview without ?fixture shows helpful instructions
- [x] /preview?fixture=missing.json returns 404
- [x] /preview?fixture=valid.json renders the brief with PREVIEW MODE banner
- [x] /preview?fixture=../etc/passwd is rejected by the filename allowlist
- [ ] Vercel preview URL works end-to-end with a sample fixture"
```

- [ ] **Step 3: Wait for Vercel preview**, then visit `<preview-url>/preview?fixture=` and confirm the helpful message appears.

- [ ] **Step 4: Drop a sample fixture file** (a copy of the most recent production brief, anonymized if needed) at `public/fixtures/sample.json`, commit, push, and verify `<preview-url>/preview?fixture=sample.json` renders the brief with the yellow PREVIEW MODE banner.

- [ ] **Step 5:** **NUDGE Adnan with the preview URL. Wait for approval.**

- [ ] **Step 6:** After approval — squash-merge PR.

---

## Phase 1 — Compute layer + tests (8 tasks, 1 PR)

> **PR boundary:** Phase 1 ships as a single PR titled `feat(pipeline): history_anchors compute layer + metric_history_monthly client`. No prompt changes, no UI changes. Backend-only and tested in isolation.

### Task 1.1: Extend `brief/history.py` with `metric_history_monthly` read path

**Files:**
- Modify: `brief/history.py`
- Test: `tests/test_history.py` (extend existing)

- [ ] **Step 1: Write the failing test** in `tests/test_history.py` (append to existing tests):

```python
def test_get_latest_from_monthly_table():
    http = _StubHttp(
        {"/rest/v1/metric_history_monthly?metric_id=eq.cpi_12m_avg_monthly&order=as_of.desc&limit=1":
            (200, [{"metric_id": "cpi_12m_avg_monthly", "as_of": "2026-04-01", "value": 5.2, "source": "macro_observer_seed"}])}
    )
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    row = client.get_latest("cpi_12m_avg_monthly", table="metric_history_monthly")
    assert row is not None
    assert row.metric_id == "cpi_12m_avg_monthly"
    assert row.value == 5.2
    assert row.as_of.isoformat() == "2026-04-01"


def test_get_history_window_from_monthly_table():
    http = _StubHttp(
        {"/rest/v1/metric_history_monthly?metric_id=in.(cpi_12m_avg_monthly)&order=as_of.desc&limit=60":
            (200, [
                {"metric_id": "cpi_12m_avg_monthly", "as_of": "2026-04-01", "value": 5.2, "source": "x"},
                {"metric_id": "cpi_12m_avg_monthly", "as_of": "2026-03-01", "value": 5.4, "source": "x"},
            ])}
    )
    client = MetricHistoryClient(url="https://x", service_key="k", http=http)
    rows = client.get_history_window(["cpi_12m_avg_monthly"], limit=60, table="metric_history_monthly")
    assert len(rows["cpi_12m_avg_monthly"]) == 2
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_history.py::test_get_latest_from_monthly_table -v
```
Expected: FAIL with `TypeError` or assertion error (method doesn't take `table` kwarg yet).

- [ ] **Step 3: Modify `brief/history.py`** — extend `MetricHistoryClient` methods with optional `table` parameter:

```python
class MetricHistoryClient:
    def __init__(self, *, url: str, service_key: str, http: HttpClient | None = None):
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.http = http or UrllibHttp()

    def get_latest(self, metric_id: str, *, table: str = "metric_history") -> HistoryRow | None:
        url = (
            f"{self.url}/rest/v1/{table}"
            f"?metric_id=eq.{urllib.parse.quote(metric_id)}"
            "&order=as_of.desc&limit=1"
        )
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return None
        row = body[0]
        return HistoryRow(
            metric_id=row["metric_id"],
            as_of=date.fromisoformat(row["as_of"]),
            value=float(row["value"]) if isinstance(row["value"], (int, float, str)) else row["value"],
            source=row["source"],
        )

    def get_history_window(
        self,
        metric_ids: Sequence[str],
        *,
        limit: int = 365,
        table: str = "metric_history",
    ) -> dict[str, list[HistoryRow]]:
        ids = ",".join(metric_ids)
        url = (
            f"{self.url}/rest/v1/{table}"
            f"?metric_id=in.({ids})&order=as_of.desc&limit={limit}"
        )
        status, body = self.http.get(url, headers=self._headers())
        if status != 200 or not body:
            return {mid: [] for mid in metric_ids}
        grouped: dict[str, list[HistoryRow]] = {mid: [] for mid in metric_ids}
        for row in body:
            try:
                value = float(row["value"])
            except (TypeError, ValueError):
                continue
            grouped.setdefault(row["metric_id"], []).append(
                HistoryRow(
                    metric_id=row["metric_id"],
                    as_of=date.fromisoformat(row["as_of"]),
                    value=value,
                    source=row["source"],
                )
            )
        return grouped

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
```

(Adapt existing method signatures rather than fully rewriting if the file already has these methods — the key change is the `table` keyword.)

- [ ] **Step 4: Run tests and verify pass**

```bash
.venv/bin/pytest tests/test_history.py -v
```
Expected: all tests PASS including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add brief/history.py tests/test_history.py
git commit -m "feat(history): support metric_history_monthly read path

Extends MetricHistoryClient.get_latest and get_history_window with an
optional `table` kwarg defaulting to 'metric_history'. Callers can pass
'metric_history_monthly' to read the long-horizon monthly archive used
by EconDelta's /macro PWA and now The Brief's history_anchors layer."
```

### Task 1.2: Create `brief/history_anchors.py` with `HistoryFact` dataclass and module constants

**Files:**
- Create: `brief/history_anchors.py`
- Create: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_history_anchors.py
import pytest
from brief.history_anchors import (
    HistoryFact,
    MIN_DATA_POINTS,
    DEFAULT_WINDOW,
    CADENCE_TABLE,
)


def test_history_fact_is_frozen_dataclass():
    fact = HistoryFact(
        metric_id="cpi_12m_avg_monthly",
        kind="since_lower",
        phrase="lowest 12-month CPI since Sep 2021 (4.8% then)",
        reference_value=4.8,
        reference_value_formatted="4.8%",
        reference_as_of="2021-09-01",
    )
    assert fact.metric_id == "cpi_12m_avg_monthly"
    assert fact.kind == "since_lower"
    with pytest.raises((AttributeError, FrozenInstanceError := type)):  # frozen dataclass
        fact.kind = "vs_period"  # type: ignore[misc]


def test_min_data_points_per_cadence():
    assert MIN_DATA_POINTS["daily"] == 30
    assert MIN_DATA_POINTS["weekly"] == 12
    assert MIN_DATA_POINTS["monthly"] == 6
    assert MIN_DATA_POINTS["quarterly"] == 4
    assert MIN_DATA_POINTS["fiscal_year"] == 3


def test_default_window_per_cadence():
    assert DEFAULT_WINDOW["daily"] == 365
    assert DEFAULT_WINDOW["weekly"] == 52
    assert DEFAULT_WINDOW["monthly"] == 60
    assert DEFAULT_WINDOW["quarterly"] == 16
    assert DEFAULT_WINDOW["fiscal_year"] == 5


def test_cadence_table_routing():
    assert CADENCE_TABLE["daily"] == "metric_history"
    assert CADENCE_TABLE["weekly"] == "metric_history"
    assert CADENCE_TABLE["monthly"] == "metric_history_monthly"
    assert CADENCE_TABLE["quarterly"] == "metric_history"
    assert CADENCE_TABLE["fiscal_year"] == "metric_history"
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_history_anchors.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'brief.history_anchors'`.

- [ ] **Step 3: Create `brief/history_anchors.py`**

```python
"""History anchors compute layer.

Reads metric_history (daily/weekly/quarterly/fiscal_year) and
metric_history_monthly (monthly long-horizon) and produces HistoryFact
instances for the editor to weave into chart_read.context, banker_read.verdict,
and Section.analysis.

The compute layer is the SOLE place that formats the parenthetical reference
value phrase. The editor inlines `phrase` verbatim and is forbidden from
inventing its own parens phrasing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, Sequence

from brief.history import HistoryRow, MetricHistoryClient


HistoryKind = Literal[
    "since_lower",
    "since_higher",
    "vs_period",
    "extreme_in_window",
    "first_cross_since",
]


@dataclass(frozen=True)
class HistoryFact:
    """A pre-formatted historical anchor for the editor to inline verbatim.

    `phrase` ALREADY includes the reference value in parens — the editor must
    not append, modify, or replace the parenthetical. The editor MAY paraphrase
    the surrounding sentence.
    """
    metric_id: str
    kind: HistoryKind
    phrase: str                         # e.g. "lowest 12-month CPI since Sep 2021 (4.8% then)"
    reference_value: float              # raw numeric reference point
    reference_value_formatted: str      # e.g. "4.8%" — already embedded in `phrase`
    reference_as_of: str                # ISO date "2021-09-01" or period "Q3 2024"


# Minimum data points for "since X" claims to be statistical, not nominal.
# Below this threshold the compute layer returns no facts of that kind.
MIN_DATA_POINTS: dict[str, int] = {
    "daily":       30,
    "weekly":      12,
    "monthly":     6,
    "quarterly":   4,
    "fiscal_year": 3,
}

# Default look-back window (in data points, not calendar days — robust to gaps).
DEFAULT_WINDOW: dict[str, int] = {
    "daily":       365,
    "weekly":      52,
    "monthly":     60,
    "quarterly":   16,
    "fiscal_year": 5,
}

# Which Supabase table holds the history for each cadence.
CADENCE_TABLE: dict[str, str] = {
    "daily":       "metric_history",
    "weekly":      "metric_history",
    "monthly":     "metric_history_monthly",
    "quarterly":   "metric_history",
    "fiscal_year": "metric_history",
}
```

- [ ] **Step 4: Run tests and verify pass**

```bash
.venv/bin/pytest tests/test_history_anchors.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): scaffold module with HistoryFact + cadence config"
```

### Task 1.3: Implement `last_lower_than` primitive

**Files:**
- Modify: `brief/history_anchors.py`
- Modify: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test** (append to test file):

```python
from datetime import date as _date
from brief.history_anchors import last_lower_than, HistoryFact
from brief.history import HistoryRow


def _format_pct_1dp(v: float) -> str:
    return f"{v:.1f}%"


def _row(metric_id: str, as_of: str, value: float) -> HistoryRow:
    return HistoryRow(metric_id=metric_id, as_of=_date.fromisoformat(as_of), value=value, source="t")


def test_last_lower_than_finds_most_recent_lower():
    # History sorted most-recent-first (as PostgREST order=as_of.desc returns)
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),  # current
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.4),
        _row("cpi_12m_avg_monthly", "2026-02-01", 5.6),
        _row("cpi_12m_avg_monthly", "2021-09-01", 4.8),  # last lower
        _row("cpi_12m_avg_monthly", "2021-08-01", 5.1),
    ]
    fact = last_lower_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is not None
    assert fact.kind == "since_lower"
    assert fact.reference_value == 4.8
    assert fact.reference_value_formatted == "4.8%"
    assert fact.reference_as_of == "2021-09-01"
    assert "since Sep 2021" in fact.phrase
    assert "(4.8% then)" in fact.phrase


def test_last_lower_than_returns_none_when_no_lower_exists():
    history = [_row("x", "2026-04-01", 5.2), _row("x", "2026-03-01", 6.0)]
    # No row with value < 5.2 in the window
    history_with_higher_only = [_row("x", "2026-04-01", 5.2)] + [
        _row("x", f"2026-{m:02d}-01", 10.0) for m in range(1, 4)
    ]
    # Pad to meet min_data_points threshold
    extended = history_with_higher_only + [
        _row("x", f"2025-{m:02d}-01", 10.0) for m in range(1, 13)
    ]
    fact = last_lower_than(extended, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is None


def test_last_lower_than_returns_none_when_history_too_sparse():
    history = [_row("x", "2026-04-01", 5.2), _row("x", "2026-03-01", 4.8)]
    # Only 2 monthly data points — below MIN_DATA_POINTS["monthly"]=6
    fact = last_lower_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is None
```

- [ ] **Step 2: Run and verify failure**

```bash
.venv/bin/pytest tests/test_history_anchors.py::test_last_lower_than_finds_most_recent_lower -v
```
Expected: FAIL — `last_lower_than` not yet defined.

- [ ] **Step 3: Implement in `brief/history_anchors.py`** (append):

```python
_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_as_of(d: date, cadence: str) -> str:
    """Format a date as a banker-friendly period label.

    monthly  → 'Sep 2021'
    quarterly → 'Q3 2024'  (computed from month)
    daily/weekly → 'Sep 2021'  (month-level granularity is enough for prose)
    fiscal_year → 'FY24'  (Bangladesh FY runs Jul-Jun)
    """
    if cadence == "quarterly":
        q = (d.month - 1) // 3 + 1
        return f"Q{q} {d.year}"
    if cadence == "fiscal_year":
        # BD FY runs Jul-Jun; FY24 ends Jun 2024
        fy = d.year if d.month >= 7 else d.year - 1
        return f"FY{str(fy)[-2:]}"
    return f"{_MONTH_ABBR[d.month - 1]} {d.year}"


def last_lower_than(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    cadence: str,
    formatter: Callable[[float], str],
) -> HistoryFact | None:
    """Return a HistoryFact for the most recent row whose value is < current_value.

    `history` MUST be ordered most-recent-first (PostgREST `order=as_of.desc`).
    Returns None when:
      - fewer than MIN_DATA_POINTS[cadence] rows are available
      - no row in `history` is below `current_value`
    """
    min_pts = MIN_DATA_POINTS.get(cadence, 6)
    if len(history) < min_pts:
        return None

    metric_id = history[0].metric_id
    for row in history:
        if row.value < current_value:
            ref_formatted = formatter(row.value)
            period_label = _format_as_of(row.as_of, cadence)
            return HistoryFact(
                metric_id=metric_id,
                kind="since_lower",
                phrase=f"lowest since {period_label} ({ref_formatted} then)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None
```

- [ ] **Step 4: Run tests and verify pass**

```bash
.venv/bin/pytest tests/test_history_anchors.py -v
```
Expected: all 7 tests PASS (4 from Task 1.2 + 3 from this task).

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): add last_lower_than primitive

Returns HistoryFact when current value crosses below historical record.
Phrase pre-formatted with reference value in parens; editor inlines
verbatim per spec §3.1."
```

### Task 1.4: Implement `last_higher_than` primitive (mirror of last_lower_than)

**Files:**
- Modify: `brief/history_anchors.py`
- Modify: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
def test_last_higher_than_finds_most_recent_higher():
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.0),
        _row("cpi_12m_avg_monthly", "2022-03-01", 7.5),  # last higher
        _row("cpi_12m_avg_monthly", "2022-02-01", 6.0),
        # ... pad to meet min_data_points threshold
        *[_row("cpi_12m_avg_monthly", f"2021-{m:02d}-01", 4.0) for m in range(1, 13)],
    ]
    fact = last_higher_than(history, current_value=5.2, cadence="monthly", formatter=_format_pct_1dp)
    assert fact is not None
    assert fact.kind == "since_higher"
    assert fact.reference_value == 7.5
    assert "highest since Mar 2022" in fact.phrase
    assert "(7.5% then)" in fact.phrase
```

- [ ] **Step 2: Run** — expected FAIL (undefined).

- [ ] **Step 3: Implement** (append to `history_anchors.py`):

```python
def last_higher_than(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    cadence: str,
    formatter: Callable[[float], str],
) -> HistoryFact | None:
    """Mirror of last_lower_than — returns the most recent row above current_value."""
    min_pts = MIN_DATA_POINTS.get(cadence, 6)
    if len(history) < min_pts:
        return None

    metric_id = history[0].metric_id
    for row in history:
        if row.value > current_value:
            ref_formatted = formatter(row.value)
            period_label = _format_as_of(row.as_of, cadence)
            return HistoryFact(
                metric_id=metric_id,
                kind="since_higher",
                phrase=f"highest since {period_label} ({ref_formatted} then)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None
```

- [ ] **Step 4: Run** — expected PASS for all tests.

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): add last_higher_than primitive"
```

### Task 1.5: Implement `pct_change_since` primitive

**Files:**
- Modify: `brief/history_anchors.py`
- Modify: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pct_change_since_matches_named_period():
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 5.2),
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.4),
        _row("cpi_12m_avg_monthly", "2026-02-01", 5.5),
        _row("cpi_12m_avg_monthly", "2025-04-01", 9.4),  # YoY anchor
        *[_row("cpi_12m_avg_monthly", f"2025-{m:02d}-01", 8.5) for m in range(1, 13)],
    ]
    fact = pct_change_since(
        history,
        current_value=5.2,
        reference_as_of="2025-04-01",
        formatter=_format_pct_1dp,
        cadence="monthly",
    )
    assert fact is not None
    assert fact.kind == "vs_period"
    assert fact.reference_value == 9.4
    assert "vs Apr 2025" in fact.phrase
    assert "(9.4% then)" in fact.phrase
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement**:

```python
def pct_change_since(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    reference_as_of: str,
    formatter: Callable[[float], str],
    cadence: str,
) -> HistoryFact | None:
    """Compute the delta from current to a specific reference date.

    `reference_as_of` is an ISO date string. Looks up the exact row; returns None
    if not present (caller's responsibility to pass a date that exists in history).
    """
    target = date.fromisoformat(reference_as_of)
    for row in history:
        if row.as_of == target:
            ref_formatted = formatter(row.value)
            period_label = _format_as_of(row.as_of, cadence)
            return HistoryFact(
                metric_id=row.metric_id,
                kind="vs_period",
                phrase=f"vs {period_label} ({ref_formatted} then)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): add pct_change_since primitive"
```

### Task 1.6: Implement `rolling_extremes` primitive

**Files:**
- Modify: `brief/history_anchors.py`
- Modify: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
def test_rolling_extremes_returns_min_max_and_rank():
    history = [
        _row("brent_crude_usd_barrel", "2026-04-01", 87.20),
        _row("brent_crude_usd_barrel", "2026-03-15", 91.40),  # max
        _row("brent_crude_usd_barrel", "2026-02-01", 75.10),  # min
        *[_row("brent_crude_usd_barrel", f"2025-{m:02d}-15", 80.0 + m) for m in range(1, 13)],
        *[_row("brent_crude_usd_barrel", f"2025-{m:02d}-01", 78.0 + m) for m in range(1, 13)],
    ]
    fact = rolling_extremes(
        history,
        current_value=87.20,
        window=30,
        formatter=lambda v: f"${v:.2f}",
        cadence="daily",
    )
    assert fact is not None
    assert fact.kind == "extreme_in_window"
    # Either highlights the max or notes current rank in window — implementation choice
    assert "$" in fact.reference_value_formatted
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement**:

```python
def rolling_extremes(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    window: int,
    formatter: Callable[[float], str],
    cadence: str,
) -> HistoryFact | None:
    """Compute min/max within a window of N data points; return the more notable extreme.

    If current_value is at or near the window max OR min, return a HistoryFact
    naming the relevant extreme. If current_value sits in the middle, return None.
    """
    if len(history) < MIN_DATA_POINTS.get(cadence, 6):
        return None

    window_rows = history[:window]
    if not window_rows:
        return None

    values = [r.value for r in window_rows]
    win_min = min(values)
    win_max = max(values)

    # Compute current_value's rank in window (lower index = higher value)
    sorted_desc = sorted(values, reverse=True)
    try:
        rank_high = sorted_desc.index(current_value) + 1  # 1 = highest
    except ValueError:
        rank_high = None

    # Notable if current is exact max, exact min, or in top/bottom 5 of window
    if current_value == win_max:
        # Find the row that previously held the max (excluding current)
        prior_max = max((r for r in window_rows[1:]), key=lambda r: r.value, default=None)
        if prior_max is None:
            return None
        return HistoryFact(
            metric_id=window_rows[0].metric_id,
            kind="extreme_in_window",
            phrase=f"highest in {window}-period window (prior {formatter(prior_max.value)} on {_format_as_of(prior_max.as_of, cadence)})",
            reference_value=prior_max.value,
            reference_value_formatted=formatter(prior_max.value),
            reference_as_of=prior_max.as_of.isoformat(),
        )
    if current_value == win_min:
        prior_min = min((r for r in window_rows[1:]), key=lambda r: r.value, default=None)
        if prior_min is None:
            return None
        return HistoryFact(
            metric_id=window_rows[0].metric_id,
            kind="extreme_in_window",
            phrase=f"lowest in {window}-period window (prior {formatter(prior_min.value)} on {_format_as_of(prior_min.as_of, cadence)})",
            reference_value=prior_min.value,
            reference_value_formatted=formatter(prior_min.value),
            reference_as_of=prior_min.as_of.isoformat(),
        )
    if rank_high and rank_high <= 5:
        return HistoryFact(
            metric_id=window_rows[0].metric_id,
            kind="extreme_in_window",
            phrase=f"{rank_high}th-highest in {window}-period window",
            reference_value=win_max,
            reference_value_formatted=formatter(win_max),
            reference_as_of=window_rows[0].as_of.isoformat(),
        )
    return None
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): add rolling_extremes primitive"
```

### Task 1.7: Implement `first_cross_since` primitive

**Files:**
- Modify: `brief/history_anchors.py`
- Modify: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
def test_first_cross_since_detects_threshold_cross_up():
    history = [
        _row("brent_crude_usd_barrel", "2026-04-01", 91.40),  # current — crossed above 90
        _row("brent_crude_usd_barrel", "2026-03-15", 87.00),
        _row("brent_crude_usd_barrel", "2026-03-01", 86.00),
        _row("brent_crude_usd_barrel", "2023-10-01", 92.10),  # last above threshold
        _row("brent_crude_usd_barrel", "2023-09-01", 88.00),
        *[_row("brent_crude_usd_barrel", f"2024-{m:02d}-01", 80.0) for m in range(1, 13)],
        *[_row("brent_crude_usd_barrel", f"2025-{m:02d}-01", 82.0) for m in range(1, 13)],
    ]
    fact = first_cross_since(
        history,
        current_value=91.40,
        threshold=90.0,
        direction="up",
        formatter=lambda v: f"${v:.2f}",
        cadence="daily",
    )
    assert fact is not None
    assert fact.kind == "first_cross_since"
    assert "above $90" in fact.phrase
    assert "Oct 2023" in fact.phrase
    assert "($92.10" in fact.phrase
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement**:

```python
def first_cross_since(
    history: Sequence[HistoryRow],
    *,
    current_value: float,
    threshold: float,
    direction: Literal["up", "down"],
    formatter: Callable[[float], str],
    cadence: str,
) -> HistoryFact | None:
    """Return a HistoryFact for the most recent time the metric was on the other side of `threshold`.

    direction='up' means current is above threshold; find the last time the metric was above threshold previously.
    direction='down' means current is below threshold; find the last time the metric was below threshold previously.
    """
    if len(history) < MIN_DATA_POINTS.get(cadence, 6):
        return None

    if direction == "up" and current_value <= threshold:
        return None
    if direction == "down" and current_value >= threshold:
        return None

    threshold_formatted = formatter(threshold)
    direction_word = "above" if direction == "up" else "below"

    # Skip the current row (history[0])
    for row in history[1:]:
        if (direction == "up" and row.value > threshold) or (direction == "down" and row.value < threshold):
            period_label = _format_as_of(row.as_of, cadence)
            ref_formatted = formatter(row.value)
            return HistoryFact(
                metric_id=row.metric_id,
                kind="first_cross_since",
                phrase=f"first time {direction_word} {threshold_formatted} since {period_label} ({ref_formatted} last cross)",
                reference_value=row.value,
                reference_value_formatted=ref_formatted,
                reference_as_of=row.as_of.isoformat(),
            )
    return None
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): add first_cross_since primitive"
```

### Task 1.8: Implement `compute_history_facts` orchestrator

**Files:**
- Modify: `brief/history_anchors.py`
- Modify: `tests/test_history_anchors.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compute_history_facts_combines_primitives_for_monthly_metric():
    # Monthly cadence, current value at a new low → expects since_lower fact
    history = [
        _row("cpi_12m_avg_monthly", "2026-04-01", 4.5),  # new low
        _row("cpi_12m_avg_monthly", "2026-03-01", 5.0),
        *[_row("cpi_12m_avg_monthly", f"2025-{m:02d}-01", 5.5 + m * 0.1) for m in range(1, 13)],
    ]
    facts = compute_history_facts(
        history,
        cadence="monthly",
        current_value=4.5,
        formatter=_format_pct_1dp,
    )
    assert len(facts) >= 1
    kinds = {f.kind for f in facts}
    assert "since_lower" in kinds


def test_compute_history_facts_returns_empty_for_sparse_history():
    history = [_row("x", "2026-04-01", 5.0), _row("x", "2026-03-01", 4.8)]
    facts = compute_history_facts(history, cadence="monthly", current_value=5.0, formatter=_format_pct_1dp)
    assert facts == []
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Implement** (orchestrator that calls each primitive and gathers results):

```python
def compute_history_facts(
    history: Sequence[HistoryRow],
    *,
    cadence: str,
    current_value: float | None,
    formatter: Callable[[float], str],
    rolling_window: int | None = None,
) -> list[HistoryFact]:
    """Run all primitives over a metric's history and return all non-None facts.

    Returns an empty list when:
      - current_value is None (no live value to anchor against)
      - history is shorter than MIN_DATA_POINTS for the cadence
    """
    if current_value is None:
        return []
    if len(history) < MIN_DATA_POINTS.get(cadence, 6):
        return []

    facts: list[HistoryFact] = []

    # since_lower / since_higher are mutually exclusive on the same current value
    lower = last_lower_than(history, current_value=current_value, cadence=cadence, formatter=formatter)
    if lower:
        facts.append(lower)
    else:
        higher = last_higher_than(history, current_value=current_value, cadence=cadence, formatter=formatter)
        if higher:
            facts.append(higher)

    # rolling_extremes adds a window-rank fact if current is near an extreme
    window = rolling_window or DEFAULT_WINDOW.get(cadence, 30)
    extreme = rolling_extremes(
        history,
        current_value=current_value,
        window=window,
        formatter=formatter,
        cadence=cadence,
    )
    if extreme:
        facts.append(extreme)

    return facts


def fetch_and_compute(
    client: MetricHistoryClient,
    metric_id: str,
    *,
    cadence: str,
    current_value: float | None,
    formatter: Callable[[float], str],
) -> list[HistoryFact]:
    """Pull history for a single metric and compute facts.

    Cadence-aware: chooses the right Supabase table per CADENCE_TABLE.
    """
    table = CADENCE_TABLE.get(cadence, "metric_history")
    window = DEFAULT_WINDOW.get(cadence, 365)
    grouped = client.get_history_window([metric_id], limit=window, table=table)
    history = grouped.get(metric_id, [])
    return compute_history_facts(
        history,
        cadence=cadence,
        current_value=current_value,
        formatter=formatter,
    )
```

- [ ] **Step 4: Run all history_anchors tests**

```bash
.venv/bin/pytest tests/test_history_anchors.py -v
```
Expected: all ~12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/history_anchors.py tests/test_history_anchors.py
git commit -m "feat(history_anchors): add compute_history_facts orchestrator + fetch_and_compute

Combines the 5 primitives into a single function that gathers all
non-None facts for a metric. fetch_and_compute is the cadence-aware
entry point that selects metric_history vs metric_history_monthly and
runs the full pipeline."
```

### Task 1.9: Push Phase 1 branch and open PR

**Files:** none

- [ ] **Step 1: Push branch**

```bash
git push -u origin feat/v1.4.0-phase1-history-anchors
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --head feat/v1.4.0-phase1-history-anchors \
  --title "feat(pipeline): history_anchors compute layer + metric_history_monthly client" \
  --body "Phase 1 of v1.4.0 Banker-Grade Read.

Spec: \`docs/superpowers/specs/2026-05-27-banker-grade-read-design.md\` §3.1

Adds \`brief/history_anchors.py\` with 5 cadence-aware primitives that
read \`metric_history\` (daily/weekly/quarterly/fiscal_year) and
\`metric_history_monthly\` (monthly long-horizon) to produce HistoryFact
instances. The compute layer is the SOLE source of pre-formatted
historical phrases — the editor inlines verbatim.

Also extends \`brief/history.py::MetricHistoryClient\` with a \`table\`
kwarg to support the monthly archive.

No prompt changes, no UI changes — pure backend addition. Tested in
isolation with ~12 unit tests.

## Test plan
- [x] All history_anchors unit tests pass (12 tests)
- [x] No regression in existing test_history.py tests (extended with 2 new)
- [ ] Reviewer confirms primitive set matches spec §3.1"
```

- [ ] **Step 3:** Merge Phase 1 PR before starting Phase 3 (Phase 2 can run in parallel).

---

## Phase 2 — Validators + sub-editor + Master.md (8 tasks, 1 PR)

> **PR boundary:** Phase 2 ships as a single PR titled `feat(validators): banker-grade specificity enforcement + abbreviation tiers`. Can run in parallel with Phase 1 (no shared files). Web search wiring (Task 2.7) is **CONDITIONAL on Phase 0 Task 0.1 GREEN outcome** — skip if RED.

> Before starting, switch branches: `git switch main && git pull --ff-only && git switch -c feat/v1.4.0-phase2-validators`

### Task 2.1: Add module constants to `validators.py`

**Files:**
- Modify: `brief/claude/validators.py`
- Create: `tests/test_claude_validators.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_claude_validators.py
from brief.claude.validators import (
    BANAL_TOKENS,
    TEMPORAL_TOKENS,
    DESK_WORDS,
    ACTION_VERBS,
    TIER1_ABBREVS,
    TIER2_ABBREVS_AND_EXPANSIONS,
)


def test_banal_tokens_includes_known_ai_tells():
    assert "delve" in BANAL_TOKENS
    assert "myriad" in BANAL_TOKENS
    assert "tapestry" in BANAL_TOKENS
    assert "amid" in BANAL_TOKENS
    assert "moreover" in BANAL_TOKENS


def test_temporal_tokens_includes_anchor_words():
    assert "since" in TEMPORAL_TOKENS
    assert "vs" in TEMPORAL_TOKENS
    assert "last" in TEMPORAL_TOKENS
    assert "above" in TEMPORAL_TOKENS


def test_desk_words_includes_banker_vocab():
    assert "treasury" in DESK_WORDS
    assert "alm" in DESK_WORDS
    assert "alco" in DESK_WORDS
    assert "lcr" in DESK_WORDS


def test_action_verbs_includes_decisional_verbs():
    assert "watch" in ACTION_VERBS
    assert "expect" in ACTION_VERBS
    assert "tighten" in ACTION_VERBS


def test_tier1_abbreviations_includes_bb_and_friends():
    assert "BB" in TIER1_ABBREVS
    assert "NBR" in TIER1_ABBREVS
    assert "MPS" in TIER1_ABBREVS
    assert "NPL" in TIER1_ABBREVS
    assert "USD/BDT" in TIER1_ABBREVS


def test_tier2_expansions_includes_prudential_ratios():
    assert TIER2_ABBREVS_AND_EXPANSIONS["LCR"] == "Liquidity Coverage Ratio"
    assert TIER2_ABBREVS_AND_EXPANSIONS["NSFR"] == "Net Stable Funding Ratio"
    assert TIER2_ABBREVS_AND_EXPANSIONS["REER"] == "Real Effective Exchange Rate"
```

- [ ] **Step 2: Run** — expected FAIL with ImportError.

- [ ] **Step 3: Append to `brief/claude/validators.py`**:

```python
import re

# Module-level constants for banker-grade specificity validators.

BANAL_TOKENS = frozenset({
    # AI tells
    "delve", "myriad", "tapestry", "navigate", "intricate", "robust",
    # journalese
    "amid", "moreover", "stunning move", "in a development",
    # hedging without source
    "could potentially", "may possibly", "it remains to be seen",
    # vague time
    "in coming weeks", "in the coming months",
})

TEMPORAL_TOKENS = frozenset({
    "since", "vs", "last", "above", "below", "back to", "next",
})

# Match Jan/Feb/.../Dec, Q1-Q4, and 20YY years
TEMPORAL_REGEX = re.compile(
    r"\b("
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    r"|Q[1-4]"
    r"|20\d{2}"
    r")\b",
    re.IGNORECASE,
)

DESK_WORDS = frozenset({
    "treasury", "credit", "risk", "alm", "alco", "manco",
    "lcr", "rwa", "npl", "car", "tier-1", "tier-2", "primary dealer",
    "remittance", "import lc", "export lc", "fdr", "deposit",
})

ACTION_VERBS = frozenset({
    "watch", "expect", "position", "brace", "firm", "soften",
    "tighten", "ease", "widen", "narrow", "anchor", "signal",
    "hold", "pause", "cut", "hike",
})

# Tier-1: bare use always, never expand
TIER1_ABBREVS = frozenset({
    # Institutions
    "BB", "NBR", "BSEC", "IMF", "WB", "ADB", "GoB",
    # Policy
    "MPS", "MPC", "ADP", "SDF", "SLF", "CRR", "SLR",
    # Instruments
    "T-Bill", "T-Bond", "FDR",
    # Markets
    "USD/BDT", "NPL", "ALCO", "MANCO",
    # Capital
    "Tier-1", "Tier-2",
    # Time
    "YoY", "MoM", "QoQ", "MTD", "YTD", "FY", "H1", "H2",
    "Q1", "Q2", "Q3", "Q4",
    # Units (handled as tokens, not abbreviations per se, but listed for completeness)
    "bp", "cr", "Tk",
})

# Tier-2: expand on first use per section, bare thereafter
TIER2_ABBREVS_AND_EXPANSIONS = {
    # Prudential ratios
    "LCR":   "Liquidity Coverage Ratio",
    "NSFR":  "Net Stable Funding Ratio",
    "RWA":   "Risk-Weighted Assets",
    "CAR":   "Capital Adequacy Ratio",
    "CRAR":  "Capital to Risk-weighted Assets Ratio",
    # Risk
    "ALM":   "Asset-Liability Management",
    "DPD":   "Days Past Due",
    "ECL":   "Expected Credit Loss",
    # Treasury
    "FRA":   "Forward Rate Agreement",
    "IRS":   "Interest Rate Swap",
    "REER":  "Real Effective Exchange Rate",
    "NEER":  "Nominal Effective Exchange Rate",
    # Banks
    "SCB":   "State-Owned Commercial Bank",
    "GSIB":  "Global Systemically Important Bank",
    "D-SIB": "Domestic Systemically Important Bank",
}
```

- [ ] **Step 4: Run** — expected PASS for all 6 constant tests.

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/test_claude_validators.py
git commit -m "feat(validators): add banker-grade specificity constants

BANAL_TOKENS, TEMPORAL_TOKENS, DESK_WORDS, ACTION_VERBS, TIER1_ABBREVS,
TIER2_ABBREVS_AND_EXPANSIONS. Module constants used by 6 new validators
shipping later in this PR."
```

### Task 2.2: Implement `validate_no_banal_language`

**Files:**
- Modify: `brief/claude/validators.py`
- Modify: `tests/test_claude_validators.py`

- [ ] **Step 1: Write the failing test**

```python
def test_validate_no_banal_language_passes_clean_text():
    result = validate_no_banal_language("Brent +2.4% to $87.20, third weekly gain since Q2 2024.")
    assert result.ok


def test_validate_no_banal_language_fails_on_delve():
    result = validate_no_banal_language("We delve into the implications for ALCO.")
    assert not result.ok
    assert "delve" in result.reason.lower()


def test_validate_no_banal_language_fails_on_amid():
    result = validate_no_banal_language("Sentiment soured amid policy uncertainty.")
    assert not result.ok


def test_validate_no_banal_language_is_case_insensitive():
    result = validate_no_banal_language("Markets navigate INTRICATE terrain.")
    assert not result.ok
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Add to `validators.py`**:

```python
def validate_no_banal_language(text: str) -> ValidationResult:
    """Reject text containing AI-tell tokens, journalese, or vague hedging."""
    lower = text.lower()
    hits = sorted(token for token in BANAL_TOKENS if token in lower)
    if hits:
        return ValidationResult(False, reason=f"banal language present: {hits}")
    return ValidationResult(True)
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/test_claude_validators.py
git commit -m "feat(validators): add validate_no_banal_language"
```

### Task 2.3: Implement `validate_chart_read_temporal_anchor`

**Files:**
- Modify: `brief/claude/validators.py`
- Modify: `tests/test_claude_validators.py`

- [ ] **Step 1: Write the failing test**

```python
def test_validate_chart_read_temporal_anchor_passes_with_since():
    chart_read = {
        "signal": "Brent +2.4% to $87.20.",
        "context": "Highest since Q2 2024 ($91.40 then).",
        "implication": "Watch H2 import bills.",
    }
    assert validate_chart_read_temporal_anchor(chart_read).ok


def test_validate_chart_read_temporal_anchor_passes_with_year_token():
    chart_read = {"signal": "x", "context": "First time above 5% in 2025.", "implication": "y"}
    assert validate_chart_read_temporal_anchor(chart_read).ok


def test_validate_chart_read_temporal_anchor_fails_without_anchor():
    chart_read = {"signal": "x", "context": "Inflation remains elevated.", "implication": "y"}
    assert not validate_chart_read_temporal_anchor(chart_read).ok
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Add**:

```python
def validate_chart_read_temporal_anchor(chart_read: dict) -> ValidationResult:
    """ChartRead.context must contain a temporal anchor token or a month/year/Q token."""
    context = chart_read.get("context", "") or ""
    if not context:
        return ValidationResult(False, reason="chart_read.context is empty")
    lower = context.lower()
    if any(token in lower for token in TEMPORAL_TOKENS):
        return ValidationResult(True)
    if TEMPORAL_REGEX.search(context):
        return ValidationResult(True)
    return ValidationResult(
        False,
        reason="chart_read.context lacks temporal anchor (need 'since'/'vs'/'last'/'above'/'below'/'next' or a month/year/Q token)",
    )
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/test_claude_validators.py
git commit -m "feat(validators): add validate_chart_read_temporal_anchor"
```

### Task 2.4: Implement `validate_chart_read_implication_quality`

**Files:**
- Modify: `brief/claude/validators.py`
- Modify: `tests/test_claude_validators.py`

- [ ] **Step 1: Write the failing test**

```python
def test_validate_chart_read_implication_quality_passes_with_desk_word():
    chart_read = {"signal": "x", "context": "y", "implication": "Watch ALCO positioning."}
    assert validate_chart_read_implication_quality(chart_read).ok


def test_validate_chart_read_implication_quality_passes_with_action_verb():
    chart_read = {"signal": "x", "context": "y", "implication": "Expect rate hold next MPS."}
    assert validate_chart_read_implication_quality(chart_read).ok


def test_validate_chart_read_implication_quality_fails_on_generic():
    chart_read = {"signal": "x", "context": "y", "implication": "May affect the economy."}
    assert not validate_chart_read_implication_quality(chart_read).ok
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Add**:

```python
def validate_chart_read_implication_quality(chart_read: dict) -> ValidationResult:
    """ChartRead.implication must contain desk word OR action verb OR time anchor."""
    impl = chart_read.get("implication", "") or ""
    if not impl:
        return ValidationResult(False, reason="chart_read.implication is empty")
    lower = impl.lower()
    has_desk = any(w in lower for w in DESK_WORDS)
    has_verb = any(v in lower for v in ACTION_VERBS)
    has_time = any(t in lower for t in TEMPORAL_TOKENS) or bool(TEMPORAL_REGEX.search(impl))
    if has_desk or has_verb or has_time:
        return ValidationResult(True)
    return ValidationResult(
        False,
        reason="chart_read.implication needs at least one of: desk word (treasury/ALCO/...), action verb (watch/expect/...), or time anchor",
    )
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/test_claude_validators.py
git commit -m "feat(validators): add validate_chart_read_implication_quality"
```

### Task 2.5: Implement `validate_chart_read_length` and `validate_history_claim_has_reference`

**Files:**
- Modify: `brief/claude/validators.py`
- Modify: `tests/test_claude_validators.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_validate_chart_read_length_passes_under_caps():
    chart_read = {
        "signal": " ".join(["word"] * 25),       # exactly 25
        "context": " ".join(["word"] * 20),      # exactly 20
        "implication": " ".join(["word"] * 25),  # exactly 25
    }
    assert validate_chart_read_length(chart_read).ok


def test_validate_chart_read_length_fails_on_signal_over_25():
    chart_read = {"signal": " ".join(["word"] * 26), "context": "x", "implication": "y"}
    result = validate_chart_read_length(chart_read)
    assert not result.ok
    assert "signal" in result.reason


def test_validate_chart_read_length_fails_on_context_over_20():
    chart_read = {"signal": "x", "context": " ".join(["w"] * 21), "implication": "y"}
    result = validate_chart_read_length(chart_read)
    assert not result.ok
    assert "context" in result.reason


def test_validate_history_claim_has_reference_passes_with_parens():
    used_facts = [{
        "phrase": "lowest 12-month CPI since Sep 2021 (4.8% then)",
        "reference_value_formatted": "4.8%",
    }]
    text = "Inflation eased to 5.2% — lowest 12-month CPI since Sep 2021 (4.8% then)."
    assert validate_history_claim_has_reference(text, used_facts).ok


def test_validate_history_claim_has_reference_fails_when_parens_dropped():
    used_facts = [{
        "phrase": "lowest 12-month CPI since Sep 2021 (4.8% then)",
        "reference_value_formatted": "4.8%",
    }]
    text = "Inflation eased to 5.2% — lowest 12-month CPI since Sep 2021."  # parens dropped
    result = validate_history_claim_has_reference(text, used_facts)
    assert not result.ok
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Add**:

```python
def validate_chart_read_length(chart_read: dict) -> ValidationResult:
    """Enforce 25/20/25-word caps on signal/context/implication."""
    def _wc(s: str) -> int:
        return len(s.split()) if s else 0

    caps = (("signal", 25), ("context", 20), ("implication", 25))
    for field, cap in caps:
        wc = _wc(chart_read.get(field, ""))
        if wc > cap:
            return ValidationResult(False, reason=f"chart_read.{field} exceeds {cap} words (got {wc})")
    return ValidationResult(True)


def validate_history_claim_has_reference(text: str, used_facts: list[dict]) -> ValidationResult:
    """Every historical-anchor claim cited from history_facts must preserve its parens phrase.

    `used_facts` is a list of fact dicts whose `phrase` field is the canonical
    parenthetical-bearing text the editor was supposed to inline verbatim.
    """
    for fact in used_facts:
        phrase = fact.get("phrase", "")
        if not phrase:
            continue
        # Extract the parens substring from the canonical phrase
        # e.g. "(4.8% then)" or "($91.40 last cross)"
        m = re.search(r"\([^)]+\)", phrase)
        if not m:
            continue
        parens = m.group(0)
        if parens not in text:
            return ValidationResult(
                False,
                reason=f"history-claim parens reference missing from text: {parens!r}",
            )
    return ValidationResult(True)
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/test_claude_validators.py
git commit -m "feat(validators): add validate_chart_read_length + validate_history_claim_has_reference"
```

### Task 2.6: Implement `validate_abbreviation_policy`

**Files:**
- Modify: `brief/claude/validators.py`
- Modify: `tests/test_claude_validators.py`

- [ ] **Step 1: Write the failing test**

```python
def test_validate_abbreviation_policy_passes_when_tier2_expanded_on_first_use():
    text = (
        "LCR (Liquidity Coverage Ratio) pressure rises in mid-tier banks. "
        "LCR will tighten further if BB acts."
    )
    assert validate_abbreviation_policy(
        text,
        tier1_set=TIER1_ABBREVS,
        tier2_expansions=TIER2_ABBREVS_AND_EXPANSIONS,
    ).ok


def test_validate_abbreviation_policy_fails_when_tier2_unexpanded():
    text = "LCR pressure rises in mid-tier banks. Treasury desks should watch the rate."
    result = validate_abbreviation_policy(
        text,
        tier1_set=TIER1_ABBREVS,
        tier2_expansions=TIER2_ABBREVS_AND_EXPANSIONS,
    )
    assert not result.ok
    assert "LCR" in result.reason


def test_validate_abbreviation_policy_allows_tier1_bare():
    text = "NPL ratio at 35.7% — BB MPS due Wednesday."
    assert validate_abbreviation_policy(
        text,
        tier1_set=TIER1_ABBREVS,
        tier2_expansions=TIER2_ABBREVS_AND_EXPANSIONS,
    ).ok
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Add**:

```python
def validate_abbreviation_policy(
    text: str,
    *,
    tier1_set: frozenset[str],
    tier2_expansions: dict[str, str],
) -> ValidationResult:
    """Per-section text: every Tier-2 abbreviation's first occurrence must be expanded.

    Tier-1 abbreviations are allowed bare. Tier-2 must be 'LCR (Liquidity Coverage Ratio)'
    on first occurrence; bare 'LCR' thereafter is fine.
    """
    for abbr, expansion in tier2_expansions.items():
        # Build a regex that matches the bare abbreviation at a word boundary
        bare_pattern = re.compile(rf"\b{re.escape(abbr)}\b")
        expanded_pattern = re.compile(rf"\b{re.escape(abbr)}\s*\(\s*{re.escape(expansion)}\s*\)")

        bare_matches = list(bare_pattern.finditer(text))
        if not bare_matches:
            continue  # not used in this text — fine

        # Find the FIRST occurrence position
        first_occurrence = bare_matches[0].start()

        # Check if the expanded form appears at or before the first bare occurrence
        expanded_matches = list(expanded_pattern.finditer(text))
        if not expanded_matches:
            return ValidationResult(
                False,
                reason=f"Tier-2 abbreviation {abbr!r} used without first-use expansion",
            )
        first_expansion = expanded_matches[0].start()
        if first_expansion > first_occurrence:
            return ValidationResult(
                False,
                reason=f"Tier-2 abbreviation {abbr!r} used bare before its expansion",
            )
    return ValidationResult(True)
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/claude/validators.py tests/test_claude_validators.py
git commit -m "feat(validators): add validate_abbreviation_policy

Tier-1 bare use always; Tier-2 must be expanded on first occurrence
per section. Tier-3 deferred to editor prompt + sub-editor LLM
judgment (rule-based detection is harder)."
```

### Task 2.7: Extend `subeditor_v6.txt` prompt with 7 new checklist items + (conditional) web_search tool wiring

**Files:**
- Modify: `brief/claude/prompts/subeditor_v6.txt`
- Modify: `brief/claude/max_client.py` (if Phase 0 verified web_search support)

> **Conditional:** Steps 4-5 (web_search wiring) happen ONLY if Phase 0 Task 0.1 returned GREEN. If RED, omit and proceed to Step 6.

- [ ] **Step 1: Read current subeditor_v6.txt to locate the checklist section.**

```bash
grep -n "CHECKLIST" brief/claude/prompts/subeditor_v6.txt
```

- [ ] **Step 2: Add 7 new checklist items.** Append immediately after the existing CHECKLIST entries:

```text
8. SPECIFICITY — Every interpretive field (banker_read.verdict, chart_read.implication, analysis paragraphs) must pass the time-anchored AND implications-oriented filters. Reject:
   - banal language like "amid", "moreover", "delve", "remains elevated", "in coming weeks"
   - claims without a desk word (treasury/credit/risk/ALCO/...), an action verb (watch/expect/...), or a time anchor
   If found → set verdict="revise" and rewrite to make the implication banker-grade.

9. CHART_READ.CONTEXT TEMPORAL ANCHOR — Every Section with a chart MUST have chart_read.context that contains either "since"/"vs"/"last"/"above"/"below"/"next"/"back to" OR a month/quarter/year token (Jan-Dec, Q1-Q4, 20YY). Reject otherwise.

10. HISTORY CLAIM AUDIT — Every claim of the shape "lowest/highest since X" or "first time above/below Y since Z" MUST trace to an item in the section's history_facts input. The editor was instructed to use the `phrase` field VERBATIM including parens. If a hallucinated historical claim appears (one not in history_facts) → revise: rewrite without the claim, or fail if it's load-bearing.

11. HISTORY REFERENCE-VALUE PRESERVATION — When the editor cites a since_lower/since_higher/first_cross_since fact, the parenthetical reference value in the original fact.phrase MUST appear unchanged in the output. E.g., if fact.phrase = "lowest 12-month CPI since Sep 2021 (4.8% then)", the text must contain "(4.8% then)" exactly. If parens dropped → revise to reinsert.

12. BANAL LANGUAGE — Search interpretive fields for these blocked tokens: delve, myriad, tapestry, navigate, intricate, robust, amid, moreover, stunning move, in a development, could potentially, may possibly, it remains to be seen, in coming weeks, in the coming months. If any present → revise.

13. ABBREVIATION POLICY — Per Section entry in the briefs JSON output:
    - Tier-1 (BB, NBR, MPS, NPL, ALCO, MANCO, USD/BDT, YoY, etc.) — bare use always allowed.
    - Tier-2 (LCR, NSFR, RWA, CAR, CRAR, ALM, DPD, ECL, FRA, IRS, REER, NEER, SCB, GSIB, D-SIB) — MUST be expanded on first occurrence per section, e.g. "LCR (Liquidity Coverage Ratio)". Bare use thereafter in the same section is fine.
    - Tier-3 (Basel III, ICAAP, IFRS, etc.) — expand every occurrence OR rephrase to a 2-3 word noun phrase.
    If a Tier-2 abbreviation appears bare before its expansion in a section → revise to add the expansion at first use.
```

- [ ] **Step 3:** If Phase 0 GREEN: continue to Step 4. If Phase 0 RED: skip to Step 6.

- [ ] **Step 4 (conditional):** Add web search check #14 to subeditor_v6.txt:

```text
14. WEB SEARCH SANITY CHECK (CONDITIONAL — uses web_search tool when available) — For up to 3 historical claims of kind since_lower/since_higher/first_cross_since, run a web_search to verify against published sources. Per-search timeout: 5 seconds. Total budget: 15 seconds. Decision:
    - Confirms claim: no action
    - No signal / sources thin: no action (trust EconDelta)
    - Contradicts EconDelta with >25% delta on metric value OR a different reference period: revise — soften or omit, log divergence
    - Contradicts with ≤25% delta and same reference period: log only (noise; trust EconDelta)
    If web_search tool unavailable or errors out → proceed without verification. Never block the brief on web search.
```

- [ ] **Step 5 (conditional):** Wire web_search in `brief/claude/max_client.py`. The exact API depends on Phase 0's findings — typical shape:

```python
# In max_client.py — extend the existing message-call helper used by the sub-editor
# to accept a `tools` parameter, passing through:
tools_for_subeditor = [{"type": "web_search_20250305", "name": "web_search"}]

response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=8000,
    tools=tools_for_subeditor,
    messages=[{"role": "user", "content": subeditor_prompt}],
)
```

The plan implementer should look at the actual current sub-editor call site in max_client.py (or the orchestrator) and integrate cleanly.

- [ ] **Step 6: Test the prompt change indirectly** — there's no unit test for prompt text. Instead, run the dry-run pipeline locally to verify the sub-editor still produces parseable JSON:

```bash
set -a && source /tmp/brief.env && set +a
.venv/bin/python -m brief.cli run --publish --dry-run --no-notify --today=2026-05-27
```
Expected: pipeline completes with exit code 3 (dry-run-ok). Subeditor output JSON valid.

- [ ] **Step 7: Commit**

```bash
git add brief/claude/prompts/subeditor_v6.txt
# If web_search wiring shipped:
git add brief/claude/max_client.py
git commit -m "feat(subeditor): add 7 specificity checks (+web_search if available)

Extends the sub-editor prompt with checks 8-13 covering specificity,
temporal anchor on chart_read.context, history claim audit, history
reference value preservation, banal language, and abbreviation policy.

If Phase 0 verified web_search support, also adds check 14 for
historical claim sanity-checking against the wider web (budgeted to
3 calls per brief, 5s per call, 15s total, hard fail-open)."
```

### Task 2.8: Extend `Master.md` with Banker Vocabulary Tiers subsection

**Files:**
- Modify: `Master.md`

- [ ] **Step 1: Locate insertion point.** Master.md has a "Preferred abbreviations" table and an "Avoid" table. The new "Banker vocabulary tiers" subsection slots between them.

```bash
grep -n "### Preferred abbreviations\|### Avoid" Master.md
```

- [ ] **Step 2: Insert new subsection.** After the "Preferred abbreviations" table and before the "### Avoid" heading, add:

```markdown
### Banker vocabulary tiers

The brief uses banker-domain abbreviations heavily. To keep editorial copy scannable for senior bankers without losing readers from adjacent desks, three tiers govern usage:

**Tier 1 — bare use always (never expand).** Daily banker vocab; every Tier-1 reader knows these.

| Category | Abbreviations |
|---|---|
| Institutions | BB, NBR, BSEC, IMF, WB, ADB, GoB |
| Policy | MPS, MPC, ADP, SDF, SLF, CRR, SLR |
| Instruments | T-Bill, T-Bond, FDR |
| Markets | USD/BDT, NPL, ALCO, MANCO |
| Capital | Tier-1, Tier-2 |
| Time | YoY, MoM, QoQ, MTD, YTD, FY, H1, H2, Q1-Q4 |
| Units | bp, cr, Tk, $ |

**Tier 2 — expand on first use per section, bare thereafter.** First occurrence in a section: `LCR (Liquidity Coverage Ratio)`. Subsequent occurrences in the same section: `LCR`. Each section accounts independently — if "LCR" appears in Banking and again in FX, both need the expansion on first use.

| Abbreviation | Expansion |
|---|---|
| LCR | Liquidity Coverage Ratio |
| NSFR | Net Stable Funding Ratio |
| RWA | Risk-Weighted Assets |
| CAR | Capital Adequacy Ratio |
| CRAR | Capital to Risk-weighted Assets Ratio |
| ALM | Asset-Liability Management |
| DPD | Days Past Due |
| ECL | Expected Credit Loss |
| FRA | Forward Rate Agreement |
| IRS | Interest Rate Swap |
| REER | Real Effective Exchange Rate |
| NEER | Nominal Effective Exchange Rate |
| SCB | State-Owned Commercial Bank |
| GSIB | Global Systemically Important Bank |
| D-SIB | Domestic Systemically Important Bank |

**Tier 3 — always expand, or rephrase to a 2-3 word noun phrase.** Anything not in Tier 1 or Tier 2. If forced to use, expand every occurrence; otherwise rephrase. Examples: Basel III, ICAAP, IFRS, IBOR, ESG, KYC/AML. Prefer "under Basel capital framework" over "under Basel III."

```

- [ ] **Step 3: Verify Master.md still renders correctly** (visual eyeball — the markdown renderer should show three subsections under the abbreviations theme).

- [ ] **Step 4: Commit**

```bash
git add Master.md
git commit -m "docs(master): add Banker vocabulary tiers section

Extends the existing Preferred abbreviations table with Tier 2 (expand
on first use) and Tier 3 (always expand) policy tables. Per VISION.md,
Master.md changes need sign-off — covered by the spec PR #90 review."
```

### Task 2.9: Push Phase 2 branch and open PR

**Files:** none

- [ ] **Step 1: Push**

```bash
git push -u origin feat/v1.4.0-phase2-validators
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --head feat/v1.4.0-phase2-validators \
  --title "feat(validators): banker-grade specificity enforcement + abbreviation tiers" \
  --body "Phase 2 of v1.4.0 Banker-Grade Read.

Spec: \`docs/superpowers/specs/2026-05-27-banker-grade-read-design.md\` §3.3 / §3.4 / §3.5

Adds 6 new validators to \`brief/claude/validators.py\`:
- validate_no_banal_language
- validate_chart_read_temporal_anchor
- validate_chart_read_implication_quality
- validate_chart_read_length (25/20/25-word caps)
- validate_history_claim_has_reference
- validate_abbreviation_policy

Extends \`subeditor_v6.txt\` with 7 new checklist items (specificity,
temporal anchor, history audit, reference preservation, banal scan,
abbreviation policy, web_search if available).

Extends \`Master.md\` with a Banker Vocabulary Tiers subsection (Tier 2
+ Tier 3 expansion tables).

If Phase 0 returned GREEN for Anthropic SDK web_search, also wires the
tool into the sub-editor with 3-call budget + 5s/15s timeouts.

## Test plan
- [x] 25+ unit tests in tests/test_claude_validators.py pass
- [x] Dry-run pipeline produces parseable sub-editor JSON
- [ ] Reviewer confirms Master.md tier lists match spec §3.3"
```

- [ ] **Step 3:** Merge Phase 2 PR before Phase 3 starts.

---

## Phase 3 — Editor prompt + macro builder + CPI chart config (10 tasks, 1 PR)

> **PR boundary:** Phase 3 ships as a single PR titled `feat(editor+macro): banker-grade prompt + 8-metric macro section + CPI chart`. Requires Phases 1 and 2 to be merged.

> Before starting: `git switch main && git pull --ff-only && git switch -c feat/v1.4.0-phase3-editor-macro`

### Task 3.1: Add `history_facts` field to `SectionData`

**Files:**
- Modify: `brief/schema.py`
- Modify: `tests/test_schema.py` (extend existing)

- [ ] **Step 1: Write the failing test**

```python
def test_section_data_has_history_facts_field():
    from brief.schema import SectionData
    from brief.history_anchors import HistoryFact
    fact = HistoryFact(
        metric_id="cpi_12m_avg_monthly",
        kind="since_lower",
        phrase="lowest 12-month CPI since Sep 2021 (4.8% then)",
        reference_value=4.8,
        reference_value_formatted="4.8%",
        reference_as_of="2021-09-01",
    )
    sd = SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=[],
        history_facts=[fact],
    )
    assert sd.history_facts == [fact]


def test_section_data_history_facts_defaults_to_empty():
    from brief.schema import SectionData
    sd = SectionData(id="macro", title="Macro & Inflation", metrics=[])
    assert sd.history_facts == []
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Modify `brief/schema.py`** — add `history_facts` field to `SectionData`:

```python
# Find the existing SectionData dataclass and add:
from brief.history_anchors import HistoryFact

@dataclass
class SectionData:
    id: str
    title: str
    metrics: list[Metric] = field(default_factory=list)
    # ... existing fields ...
    history_facts: list[HistoryFact] = field(default_factory=list)
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/schema.py tests/test_schema.py
git commit -m "feat(schema): add history_facts field to SectionData

Per spec §3.2 — builders attach pre-computed HistoryFact instances so
the editor can weave them into chart_read.context, banker_read.verdict,
and analysis prose."
```

### Task 3.2: Rewrite `brief/builders/macro.py` — 8 monthly metrics + history_facts

**Files:**
- Modify: `brief/builders/macro.py` (rewrite)
- Modify: `brief/pipeline_v6.py` (BuilderContext — add `history_monthly` client)
- Create: `tests/test_pipeline_v6_macro_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_v6_macro_enrichment.py
from datetime import date
from unittest.mock import MagicMock
from brief.builders.macro import build
from brief.builders import BuilderContext


def test_macro_builder_reads_8_monthly_metrics():
    history_monthly = MagicMock()
    history_monthly.get_latest.side_effect = lambda mid, table=None: MagicMock(
        metric_id=mid,
        as_of=date(2026, 4, 1),
        value=5.2 if "cpi" in mid else 1.5,
    )
    history_monthly.get_history_window.return_value = {
        "cpi_12m_avg_monthly": [...],
    }

    ctx = BuilderContext(
        today=date(2026, 5, 27),
        history=None,
        history_monthly=history_monthly,
        # ... other fields with mocks/defaults
    )
    section = build(ctx)
    assert section.id == "macro"
    metric_ids = [m.id for m in section.metrics]
    assert "cpi_12m_avg_monthly" in metric_ids
    assert "cpi_p2p_food_monthly" in metric_ids
    assert "real_policy_rate_monthly" in metric_ids
    assert "reer_monthly" in metric_ids
    assert len(metric_ids) == 8
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Rewrite `brief/builders/macro.py`**:

```python
"""Builder: Macro (CPI + Policy + REER + Credit + External). Monthly cadence.

Reads 8 banker-essential monthly metrics from metric_history_monthly via
the brief.history client (using the `table` kwarg added in Phase 1).
Computes HistoryFacts via brief.history_anchors and attaches them to the
returned SectionData so the editor can weave them into prose.

Per spec §3.6 — this is the macro section's per-section override on the
5-metric cap; the editor prompt explicitly allows 8 metrics here.
"""
from __future__ import annotations

from typing import Callable

from brief.cadence import section_freshness
from brief.history_anchors import HistoryFact, fetch_and_compute
from brief.schema import Metric, SectionData
from . import BuilderContext


# (metric_id, label, unit, source, format_kind)
_MACRO_METRICS: tuple[tuple[str, str, str, str, str], ...] = (
    ("cpi_12m_avg_monthly",             "CPI 12m Avg",           "%",      "BBS",     "percent-1dp"),
    ("cpi_p2p_food_monthly",            "CPI Food (P-to-P)",     "%",      "BBS",     "percent-1dp"),
    ("cpi_p2p_nonfood_monthly",         "CPI Non-Food (P-to-P)", "%",      "BBS",     "percent-1dp"),
    ("real_policy_rate_monthly",        "Real Policy Rate",      "%",      "BB+BBS",  "percent-1dp"),
    ("reer_monthly",                    "REER",                  "index",  "BB",      "comma-2dp"),
    ("private_credit_growth_yoy_monthly", "Private Credit YoY",  "%",      "BB",      "percent-1dp"),
    ("m2_growth_yoy_monthly",           "M2 YoY",                "%",      "BB",      "percent-1dp"),
    ("import_cover_months_monthly",     "Import Cover",          "months", "BB",      "comma-1dp"),
)


def _formatter_for(format_kind: str) -> Callable[[float], str]:
    if format_kind == "percent-1dp":
        return lambda v: f"{v:.1f}%"
    if format_kind == "comma-2dp":
        return lambda v: f"{v:,.2f}"
    if format_kind == "comma-1dp":
        return lambda v: f"{v:,.1f}"
    return lambda v: f"{v}"


def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    history_facts: list[HistoryFact] = []

    for mid, label, unit, source, format_kind in _MACRO_METRICS:
        last = (
            ctx.history_monthly.get_latest(mid, table="metric_history_monthly")
            if ctx.history_monthly is not None
            else None
        )
        value = last.value if last is not None else None
        as_of = last.as_of if last is not None else ctx.today
        metrics.append(Metric(
            id=mid,
            label=label,
            value=value,
            unit=unit,
            as_of=as_of,
            source=source,
            cadence="monthly",  # type: ignore[arg-type]
        ))

        if ctx.history_monthly is not None and value is not None:
            facts = fetch_and_compute(
                ctx.history_monthly,
                mid,
                cadence="monthly",
                current_value=value,
                formatter=_formatter_for(format_kind),
            )
            history_facts.extend(facts)

    return SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=metrics,
        history_facts=history_facts,
        freshness=section_freshness(metrics, today=ctx.today, section_id="macro"),
    )
```

- [ ] **Step 4: Extend `BuilderContext`** in `brief/builders/__init__.py` and `brief/pipeline_v6.py`:

```python
# brief/builders/__init__.py
from dataclasses import dataclass
from datetime import date

from brief.history import MetricHistoryClient


@dataclass
class BuilderContext:
    today: date
    history: MetricHistoryClient | None
    history_monthly: MetricHistoryClient | None     # NEW — reads metric_history_monthly
    # ... existing fields ...
```

```python
# brief/pipeline_v6.py — wherever BuilderContext is constructed
ctx = BuilderContext(
    today=today,
    history=history_client,
    history_monthly=history_client,  # same client, different table via kwarg
    # ... existing fields ...
)
```

- [ ] **Step 5: Run tests** — expected PASS.

```bash
.venv/bin/pytest tests/test_pipeline_v6_macro_enrichment.py -v
```

- [ ] **Step 6: Commit**

```bash
git add brief/builders/macro.py brief/builders/__init__.py brief/pipeline_v6.py tests/test_pipeline_v6_macro_enrichment.py
git commit -m "feat(macro): rewrite builder to read 8 monthly metrics + history_facts

Macro section now pulls cpi_12m_avg, cpi_food, cpi_nonfood, real_policy_rate,
reer, private_credit_yoy, m2_yoy, import_cover from metric_history_monthly
and attaches HistoryFacts for each. Editor prompt extension (separate task)
demands all 8 are shown — overrides the standard 5-metric cap for this
section only."
```

### Task 3.3: Wire `history_facts` into editor input

**Files:**
- Modify: `brief/pipeline_v6.py` (or `brief/v6_publisher.py` — wherever the editor input is composed)

- [ ] **Step 1: Locate where the editor input JSON is built per section.**

```bash
grep -n "history_facts\|sections.*editor\|build_editor_input" brief/pipeline_v6.py brief/v6_publisher.py
```

- [ ] **Step 2: Modify the editor input builder** to serialize `SectionData.history_facts` into the per-section JSON object:

```python
# Wherever the section dict is built for the editor input:
section_dict = {
    "slug": section_data.id,
    "title": section_data.title,
    "metrics": [...],
    "history_facts": [
        {
            "metric_id": f.metric_id,
            "kind": f.kind,
            "phrase": f.phrase,
            "reference_value_formatted": f.reference_value_formatted,
            "reference_as_of": f.reference_as_of,
        }
        for f in section_data.history_facts
    ],
    # ... other fields ...
}
```

- [ ] **Step 3: Add a test** in `tests/test_pipeline_v6_macro_enrichment.py`:

```python
def test_editor_input_includes_history_facts_for_macro():
    # Build a minimal section_data with history_facts and verify the editor
    # input dict has the expected shape.
    ...
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/pipeline_v6.py tests/test_pipeline_v6_macro_enrichment.py
git commit -m "feat(pipeline): serialize history_facts into editor input

Editor sees pre-formatted parens phrases per the v1.4.0 contract — must
inline verbatim, never invent new historical claims."
```

### Task 3.4: Extend `editor_v6.txt` with banker-grade specificity rubric

**Files:**
- Modify: `brief/claude/prompts/editor_v6.txt`

- [ ] **Step 1: Locate the existing field instructions section.**

```bash
grep -n "^# " brief/claude/prompts/editor_v6.txt
```

- [ ] **Step 2: Insert a new section** before the OUTPUT SCHEMA — STRICT JSON block:

```text
# BANKER-GRADE SPECIFICITY CONTRACT

Every interpretive field (banker_read.verdict, banker_read.watch[], banker_read.risk[],
analysis, tldr, cover.sub, chart_read.signal, chart_read.context, chart_read.implication)
must pass BOTH filters:

1. TIME-ANCHORED — names a specific period, event, or trajectory.
   GOOD: "lowest since Q2 2021", "watch Wednesday's MPS", "third consecutive monthly deceleration"
   BAD:  "remains elevated", "continues to be a concern", "in coming weeks"

2. IMPLICATIONS-ORIENTED — leads to a desk decision or mental-model update.
   GOOD: "ALM mismatch risk for FRA-tied LT loans", "expect MPC to hold given excess liquidity"
   BAD:  "may affect import bills", "could impact the economy"

Worked contrast for an oil-price chart_read:
BANAL: "Brent rose 2.4%. Higher oil prices may affect import bills."
BANKER-GRADE: "Brent +2.4% to $87.20, third weekly gain since Q2 2024. For energy-importer
              credit lines, watch H2 receivables 60-90 DPD bump on the next refi cycle."

# HISTORY_FACTS — pre-computed parens phrases (USE VERBATIM)

Every section's input includes a `history_facts` array with pre-formatted historical
anchors. The Python compute layer (brief/history_anchors.py) is the SOLE source for
"lowest since X" / "first time above Y since Z" phrases.

USE the fact.phrase field VERBATIM, including the parenthetical reference value:
  fact.phrase = "lowest 12-month CPI since Sep 2021 (4.8% then)"
  → in your output: "Inflation eased to 5.2% — lowest 12-month CPI since Sep 2021 (4.8% then)."

You MAY paraphrase the surrounding sentence. You MAY NOT:
- Modify the parens text
- Drop the parens
- Invent a different reference value
- Invent a historical claim not present in history_facts

For each chart-bearing section, weave AT LEAST ONE history_fact into chart_read.context.
For sections without a chart, weave into banker_read.verdict or analysis where it
sharpens the call.

# ABBREVIATION POLICY

Tier-1 abbreviations — use bare (never expand):
  BB, NBR, BSEC, IMF, WB, ADB, GoB, MPS, MPC, ADP, SDF, SLF, CRR, SLR, T-Bill, T-Bond,
  FDR, USD/BDT, NPL, ALCO, MANCO, Tier-1, Tier-2, YoY, MoM, QoQ, MTD, YTD, FY, H1, H2,
  Q1-Q4, bp, cr, Tk, $.

Tier-2 abbreviations — expand on first use per section, bare thereafter:
  LCR (Liquidity Coverage Ratio), NSFR (Net Stable Funding Ratio), RWA (Risk-Weighted Assets),
  CAR (Capital Adequacy Ratio), CRAR (Capital to Risk-weighted Assets Ratio),
  ALM (Asset-Liability Management), DPD (Days Past Due), ECL (Expected Credit Loss),
  FRA (Forward Rate Agreement), IRS (Interest Rate Swap), REER (Real Effective Exchange Rate),
  NEER (Nominal Effective Exchange Rate), SCB (State-Owned Commercial Bank),
  GSIB (Global Systemically Important Bank), D-SIB (Domestic Systemically Important Bank).

Tier-3 — anything not in Tier 1 or 2 must be expanded every use OR rephrased to a 2-3
word noun phrase. Examples: Basel III, ICAAP, IFRS, IBOR, ESG, KYC/AML.

# MACRO SECTION OVERRIDE

The standard rule is "drop low-signal metrics (max 5 per section)". The `macro` section
is the analytical anchor of the brief — emit ALL 8 metrics returned by the builder; do
not drop on signal grounds. The 8 macro metrics: cpi_12m_avg, cpi_p2p_food,
cpi_p2p_nonfood, real_policy_rate, reer, private_credit_yoy, m2_yoy, import_cover.
```

- [ ] **Step 3: Update the existing field instructions** for chart_read.signal/context/implication if not already present (they're new fields in v1.4.0 — they need entries in the OUTPUT SCHEMA section):

```text
      "chart_read": null | {
        "signal":      "<≤25 words, what the chart shows, direction-clear, ≥1 number, e.g. 'CPI 12m-avg eased to 5.2%, food inflation now 6.8% vs 9.4% in Mar 2025.'>",
        "context":     "<≤20 words, REQUIRED temporal anchor, includes reference value in parens verbatim from history_facts, e.g. 'First time 12m-avg below 6% since Q3 2021 (4.9% then).'>",
        "implication": "<≤25 words, desk word OR action verb OR time anchor, e.g. 'Treasury: real policy rate turns positive; expect MPC to hold next MPS.'>"
      },
```

- [ ] **Step 4: No automated tests for prompt text** — run a dry-run to verify the editor parses correctly:

```bash
.venv/bin/python -m brief.cli run --publish --dry-run --no-notify
```
Expected: pipeline completes with exit code 3 (dry-run-ok).

- [ ] **Step 5: Commit**

```bash
git add brief/claude/prompts/editor_v6.txt
git commit -m "feat(editor): banker-grade specificity contract + history_facts + abbreviations

Adds three new sections to editor_v6.txt:
1. Banker-grade specificity contract (time-anchored AND implications-oriented)
2. history_facts weaving rules (use phrase verbatim, including parens)
3. Abbreviation tier policy (Tier-1 bare / Tier-2 expand on first use / Tier-3 rephrase)
4. Macro section override (8 metrics, not 5)

Also adds chart_read field to the OUTPUT SCHEMA — the structured
signal/context/implication shape used by the new render layer (Phase 4)."
```

### Task 3.5: Mirror changes in `editor_v6_friday.txt`

**Files:**
- Modify: `brief/claude/prompts/editor_v6_friday.txt`

- [ ] **Step 1: Apply the same additions** from Task 3.4 to the Friday-variant prompt. The Friday prompt may already differ slightly from the daily prompt (e.g., weekly-wrap framing); preserve those differences and only insert the v1.4.0 additions.

- [ ] **Step 2: Verify by diff** — both editor prompts now contain the four new sections (specificity, history_facts, abbreviations, chart_read schema).

- [ ] **Step 3: Run dry-run on a Friday date**:

```bash
.venv/bin/python -m brief.cli run --publish --dry-run --no-notify --today=2026-05-29
```
Expected: pipeline completes with exit code 3.

- [ ] **Step 4: Commit**

```bash
git add brief/claude/prompts/editor_v6_friday.txt
git commit -m "feat(editor): mirror v1.4.0 banker-grade contract into Friday prompt"
```

### Task 3.6: Add `cpiTrend` chart config to `lib/chartConfigs.ts`

**Files:**
- Modify: `lib/chartConfigs.ts`

- [ ] **Step 1: Read existing chart configs** to match the style.

```bash
grep -n "function brentConfig\|function yieldCurveConfig" lib/chartConfigs.ts
```

- [ ] **Step 2: Add `cpiTrendConfig` function** following the existing line-chart pattern. Insert before the `chartConfigs` export object:

```typescript
// CPI Trend — 24-month line chart with 3 series (12m-avg headline, food, non-food).
//
// Reads three monthly series from section.series:
//   cpi_12m_avg_monthly   (headline 12-month average)
//   cpi_p2p_food_monthly  (food P-to-P)
//   cpi_p2p_nonfood_monthly (non-food P-to-P)
//
// Y-axis = percent. X-axis = 24-month TimeScale (already registered in BriefChart.tsx).

function cpiTrendConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const HEADLINE_KEY = "cpi_12m_avg_monthly";
  const FOOD_KEY = "cpi_p2p_food_monthly";
  const NONFOOD_KEY = "cpi_p2p_nonfood_monthly";

  if (!hasAnyData(ctx.series, [HEADLINE_KEY, FOOD_KEY, NONFOOD_KEY])) {
    return emptyLineConfig();
  }

  const toLineData = (key: string) =>
    (ctx.series[key] ?? []).map(p => ({ x: p.as_of, y: p.value }));

  return {
    type: "line",
    data: {
      datasets: [
        {
          label: "Headline (12m avg)",
          data: toLineData(HEADLINE_KEY),
          borderColor: "var(--steel)",
          borderWidth: 1.2,
          pointRadius: 0,
          tension: 0.25,
        },
        {
          label: "Food (P-to-P)",
          data: toLineData(FOOD_KEY),
          borderColor: "var(--tone-warn)",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.25,
        },
        {
          label: "Non-Food (P-to-P)",
          data: toLineData(NONFOOD_KEY),
          borderColor: "var(--ink-3)",
          borderWidth: 1,
          pointRadius: 0,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          type: "time",
          time: { unit: "month", tooltipFormat: "MMM yyyy" },
          ticks: { maxTicksLimit: 6, color: "var(--ink-3)" },
          grid: { display: false },
        },
        y: {
          ticks: {
            callback: v => `${v}%`,
            color: "var(--ink-3)",
          },
          grid: { color: "var(--ink-5)", drawBorder: false },
        },
      },
      plugins: {
        legend: { display: true, position: "top" as const, labels: { boxWidth: 12 } },
        tooltip: { enabled: true },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}
```

- [ ] **Step 3: Register in the `chartConfigs` export object**:

```typescript
export const chartConfigs = {
  dsex: dsexConfig,
  brent: brentConfig,
  yieldCurve: yieldCurveConfig,
  lng: lngConfig,
  fxFlows: fxFlowsConfig,
  cpiTrend: cpiTrendConfig,  // NEW
};
```

- [ ] **Step 4: Add to `SECTION_TO_CHART`**:

```typescript
export const SECTION_TO_CHART: Partial<Record<string, ChartConfigKey>> = {
  fx: "fxFlows",
  dse: "dsex",
  iran: "brent",
  // ... existing mappings ...
  macro: "cpiTrend",  // NEW
};
```

- [ ] **Step 5: Type-check + lint**

```bash
npx tsc --noEmit
npm run lint
```
Expected: clean pass.

- [ ] **Step 6: Commit**

```bash
git add lib/chartConfigs.ts
git commit -m "feat(spa): add cpiTrend chart config — 24-month CPI line chart

Three lines: headline 12m-avg, food P-to-P, non-food P-to-P. Reads
monthly metrics piped through SectionV6.series. Uses TimeScale +
LinearScale (both already registered in BriefChart.tsx per AGENTS.md
landmine #2). Wires into macro section via SECTION_TO_CHART."
```

### Task 3.7: Ensure macro section's series are populated for the CPI chart

**Files:**
- Modify: `brief/builders/macro.py`
- Modify: `brief/chart_series_fetcher.py` (extend to fetch the 3 CPI monthly series)

- [ ] **Step 1: Check current chart_series_fetcher.py for the CPI fetch path.**

```bash
grep -n "cpi\|metric_history_monthly\|series_for_section" brief/chart_series_fetcher.py
```

- [ ] **Step 2: Add a fetch path for the macro section** — pull `cpi_12m_avg_monthly`, `cpi_p2p_food_monthly`, `cpi_p2p_nonfood_monthly` from `metric_history_monthly` for the last 24 months:

```python
# In chart_series_fetcher.py — add a function or extend the existing one:
def fetch_macro_cpi_series(history_monthly: MetricHistoryClient) -> dict[str, list[SeriesPoint]]:
    """Pull 24 months of the three CPI series for the macro section's chart."""
    metric_ids = ["cpi_12m_avg_monthly", "cpi_p2p_food_monthly", "cpi_p2p_nonfood_monthly"]
    grouped = history_monthly.get_history_window(metric_ids, limit=24, table="metric_history_monthly")
    series_points: dict[str, list[SeriesPoint]] = {}
    for mid, rows in grouped.items():
        # rows are most-recent-first from PostgREST; flip to chronological for the chart
        series_points[mid] = [
            SeriesPoint(metric_id=mid, as_of=r.as_of.isoformat(), value=r.value)
            for r in reversed(rows)
        ]
    return series_points
```

- [ ] **Step 3: Wire into `brief/builders/macro.py`** — attach the series to the SectionData:

```python
def build(ctx: BuilderContext) -> SectionData:
    metrics: list[Metric] = []
    history_facts: list[HistoryFact] = []
    series: list[SeriesPoint] = []

    # ... existing metric loop ...

    # NEW — chart series for the CPI trend chart
    if ctx.history_monthly is not None:
        from brief.chart_series_fetcher import fetch_macro_cpi_series
        cpi_series_by_id = fetch_macro_cpi_series(ctx.history_monthly)
        for points in cpi_series_by_id.values():
            series.extend(points)

    return SectionData(
        id="macro",
        title="Macro & Inflation",
        metrics=metrics,
        history_facts=history_facts,
        series=series,
        freshness=section_freshness(metrics, today=ctx.today, section_id="macro"),
    )
```

- [ ] **Step 4: Add integration test** in `tests/test_pipeline_v6_macro_enrichment.py`:

```python
def test_macro_section_series_populated_with_cpi():
    # ... build a ctx with a mock history_monthly client that returns CPI rows ...
    section = build(ctx)
    series_metric_ids = {p.metric_id for p in section.series}
    assert "cpi_12m_avg_monthly" in series_metric_ids
    assert "cpi_p2p_food_monthly" in series_metric_ids
    assert "cpi_p2p_nonfood_monthly" in series_metric_ids
```

- [ ] **Step 5: Run** — expected PASS.

- [ ] **Step 6: Commit**

```bash
git add brief/builders/macro.py brief/chart_series_fetcher.py tests/test_pipeline_v6_macro_enrichment.py
git commit -m "feat(macro): fetch 24-month CPI series for the new cpiTrend chart"
```

### Task 3.8: Push Phase 3 branch and open PR

**Files:** none

- [ ] **Step 1: Push**

```bash
git push -u origin feat/v1.4.0-phase3-editor-macro
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --head feat/v1.4.0-phase3-editor-macro \
  --title "feat(editor+macro): banker-grade prompt + 8-metric macro section + CPI chart" \
  --body "Phase 3 of v1.4.0 Banker-Grade Read. Requires Phase 1 (history_anchors)
and Phase 2 (validators) merged.

Spec: \`docs/superpowers/specs/2026-05-27-banker-grade-read-design.md\` §3.2 / §3.6

- editor_v6.txt + editor_v6_friday.txt: banker-grade specificity rubric,
  history_facts weaving rules (use phrase verbatim), abbreviation tier policy,
  macro section 8-metric override, chart_read schema addition.

- brief/builders/macro.py: rewrites to read 8 banker-essential monthly metrics
  from metric_history_monthly + produce HistoryFacts via history_anchors.

- brief/pipeline_v6.py: serializes history_facts into editor input per section.

- lib/chartConfigs.ts: new cpiTrend config — 24-month line chart with 3 series.

- brief/chart_series_fetcher.py: fetches 24 months of CPI monthly series for
  the new chart.

## Test plan
- [x] Macro builder integration tests pass
- [x] Dry-run publish produces a brief with all 8 macro metrics + chart_read fields
- [ ] Vercel preview: macro section shows CPI trend chart
- [ ] Reviewer confirms editor prompt changes match spec §3.2"
```

- [ ] **Step 3:** Merge Phase 3 PR before Phase 4 starts.

---

## Phase 4 — ChartRead schema + render (5 tasks, 1 PR)

> **PR boundary:** Phase 4 ships as a single PR titled `feat(spa+schema): ChartRead field + render under every chart`. Requires Phase 3 merged.

> Before starting: `git switch main && git pull --ff-only && git switch -c feat/v1.4.0-phase4-chart-read`

### Task 4.1: Add `ChartRead` interface and `Section.chart_read` field to `types/brief.ts`

**Files:**
- Modify: `types/brief.ts`

- [ ] **Step 1: Read current `types/brief.ts`** to find the Section interface.

```bash
grep -n "^export interface Section\b" types/brief.ts
```

- [ ] **Step 2: Add `ChartRead` interface and field**:

```typescript
// types/brief.ts

export interface ChartRead {
  signal: string;        // ≤25 words, direction-clear, ≥1 number
  context: string;       // ≤20 words, REQUIRED temporal anchor + reference value
  implication: string;   // ≤25 words, desk word OR action verb OR time anchor
}

export interface Section {
  // ... existing fields preserved ...
  chart_read?: ChartRead | null;
}
```

- [ ] **Step 3: Type-check**

```bash
npx tsc --noEmit
```
Expected: clean (no consumers reference chart_read yet).

- [ ] **Step 4: Commit**

```bash
git add types/brief.ts
git commit -m "feat(types): add ChartRead interface + Section.chart_read field

Backward-compatible (optional). Previously published briefs without
chart_read render as before. Render code shipped in next task."
```

### Task 4.2: Update `brief/v6_schema.py` to validate `chart_read` JSON shape

**Files:**
- Modify: `brief/v6_schema.py`
- Modify: `tests/test_v6_schema_freshness.py` (or create `tests/test_v6_schema_chart_read.py`)

- [ ] **Step 1: Write the failing test** in `tests/test_v6_schema_chart_read.py`:

```python
import pytest
from brief.v6_schema import validate_section


def test_section_with_chart_read_passes_validation():
    section = {
        "slug": "macro",
        "title": "Macro",
        "ord": 1,
        "group_key": "markets",
        "metrics": [],
        "news": [],
        "series": [],
        "notes": [],
        "chart_read": {
            "signal": "CPI 12m-avg eased to 5.2%.",
            "context": "First time below 6% since Q3 2021 (4.9% then).",
            "implication": "Treasury: real policy rate turns positive; expect MPC to hold next MPS.",
        },
    }
    result = validate_section(section)
    assert result.ok


def test_section_with_null_chart_read_passes():
    section = {"slug": "macro", "title": "Macro", "ord": 1, "group_key": "markets",
               "metrics": [], "news": [], "series": [], "notes": [],
               "chart_read": None}
    assert validate_section(section).ok


def test_section_with_missing_chart_read_passes():
    section = {"slug": "macro", "title": "Macro", "ord": 1, "group_key": "markets",
               "metrics": [], "news": [], "series": [], "notes": []}
    assert validate_section(section).ok


def test_section_with_malformed_chart_read_fails():
    section = {"slug": "macro", "title": "Macro", "ord": 1, "group_key": "markets",
               "metrics": [], "news": [], "series": [], "notes": [],
               "chart_read": {"signal": "x"}}  # missing context + implication
    assert not validate_section(section).ok
```

- [ ] **Step 2: Run** — expected FAIL.

- [ ] **Step 3: Extend `brief/v6_schema.py`** to validate the new field:

```python
# In the validate_section function or wherever section JSON is validated:
def _validate_chart_read(cr):
    if cr is None:
        return ValidationResult(True)
    if not isinstance(cr, dict):
        return ValidationResult(False, reason="chart_read must be object or null")
    for field in ("signal", "context", "implication"):
        v = cr.get(field)
        if not isinstance(v, str):
            return ValidationResult(False, reason=f"chart_read.{field} must be a string")
    return ValidationResult(True)


# Then call _validate_chart_read(section.get("chart_read")) inside validate_section.
```

- [ ] **Step 4: Run** — expected PASS.

- [ ] **Step 5: Commit**

```bash
git add brief/v6_schema.py tests/test_v6_schema_chart_read.py
git commit -m "feat(schema): validate chart_read field in section payloads"
```

### Task 4.3: Render `chart_read` in `app/components/Section.tsx`

**Files:**
- Modify: `app/components/Section.tsx`

- [ ] **Step 1: Read current Section.tsx** to find the chart render block.

```bash
grep -n "BriefChart\|chartConfigKey" app/components/Section.tsx
```

- [ ] **Step 2: Modify the chart block** to render ChartRead paragraphs immediately under the chart:

```tsx
// In Section.tsx, find the existing BriefChart render and wrap it:

const chartConfigKey = SECTION_TO_CHART[section.slug];

return (
  <section>
    {/* ... existing header, metrics, etc. ... */}

    {chartConfigKey && (
      <>
        <BriefChart section={section} configKey={chartConfigKey} />
        {chart_read && (
          <div className="tb-analysis tb-chart-read">
            <p>{chart_read.signal}</p>
            {chart_read.context && <p>{chart_read.context}</p>}
            <p>{chart_read.implication}</p>
          </div>
        )}
      </>
    )}

    {/* ... existing banker_read, analysis, news, etc. ... */}
  </section>
);
```

- [ ] **Step 3: Destructure `chart_read` from the section prop** at the top of the component:

```tsx
const { /* ...existing... */, chart_read } = section;
```

- [ ] **Step 4: Type-check + lint**

```bash
npx tsc --noEmit
npm run lint
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/components/Section.tsx
git commit -m "feat(spa): render chart_read paragraphs under BriefChart

Three short prose paragraphs (signal/context/implication) in existing
.tb-analysis styling. No new CSS, no new component — marker class
.tb-chart-read for future targeting but ships with zero CSS rules.
Backward compatible: sections without chart_read render as before."
```

### Task 4.4: Editor instruction to populate `Cover.sub` with historical anchors

**Files:**
- Modify: `brief/claude/prompts/editor_v6.txt`
- Modify: `brief/claude/prompts/editor_v6_friday.txt`

- [ ] **Step 1: Locate the cover_metric definition in editor_v6.txt**.

```bash
grep -n "cover_metric\|cover.sub" brief/claude/prompts/editor_v6.txt
```

- [ ] **Step 2: Update the `sub` field description** in the cover_metric schema block:

```text
      "cover_metric": {
        "label":   "<KPI label, ALL CAPS short, e.g. 'NPL RATIO · Q4 2025'>",
        "value":   "<single number string with unit, e.g. '35.73%'>",
        "sub":     "<one-line context, max 60 chars. MUST include either a delta vs prior period OR an implication OR a historical anchor — NEVER bare restatement. If a HistoryFact of kind since_lower/since_higher/first_cross_since exists for this metric, prefer to inline the fact.phrase here verbatim (e.g. 'first time above $90 since 2023 ($91.40 last cross)'). Otherwise pack an implication ('liquidity squeeze pressure builds') or a delta ('+12bp WoW').>",
        "tone":    "bull|bear|warn|neu",
        ...
      },
```

- [ ] **Step 3: Mirror to `editor_v6_friday.txt`**.

- [ ] **Step 4: Commit**

```bash
git add brief/claude/prompts/editor_v6.txt brief/claude/prompts/editor_v6_friday.txt
git commit -m "feat(editor): pack historical anchors into Cover.sub when notable

No new field on Cover — historical anchors live in the existing 60-char
sub field. Editor instructed to prefer the fact.phrase verbatim when a
since_lower/since_higher/first_cross_since fact exists for the cover
metric, otherwise pack an implication or delta."
```

### Task 4.5: End-to-end dry-run smoke test + Phase 4 PR

**Files:** none

- [ ] **Step 1: Run a full local dry-run publish**

```bash
set -a && source /tmp/brief.env && set +a
.venv/bin/python -m brief.cli run --publish --dry-run --no-notify
```
Expected: exit code 3 (dry-run-ok). Inspect the dry-run output for:
- `chart_read` populated on every chart-bearing section
- `chart_read.context` contains a temporal anchor token
- `chart_read.implication` contains desk word, action verb, OR time anchor
- Macro section shows 8 metrics
- CPI trend chart's series populated

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/v1.4.0-phase4-chart-read
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --base main --head feat/v1.4.0-phase4-chart-read \
  --title "feat(spa+schema): ChartRead field + render under every chart" \
  --body "Phase 4 of v1.4.0 Banker-Grade Read. Requires Phase 3 merged.

Spec: \`docs/superpowers/specs/2026-05-27-banker-grade-read-design.md\` §3.7

- types/brief.ts: ChartRead interface + Section.chart_read field
- brief/v6_schema.py: validation
- app/components/Section.tsx: render three paragraphs in existing
  .tb-analysis styling under BriefChart
- editor_v6.txt + editor_v6_friday.txt: Cover.sub instruction to pack
  historical anchors

NO new CSS, NO new component. Marker class .tb-chart-read ships with
zero CSS rules. Backward compatible.

## Test plan
- [x] Dry-run publish populates chart_read on every chart-bearing section
- [ ] Vercel preview: chart_read prose renders under every chart
- [ ] Mobile: text density acceptable (per AGENT_LEARNINGS v1.2.1 lesson)
- [ ] Email preview: chart_read renders under chart"
```

- [ ] **Step 4:** Wait for Vercel preview to be available; eyeball each chart-bearing section in the preview deploy. **CRITICAL** — this is the visual verification gate per AGENTS.md landmine #2 (chart rendering) and the v1.2.1 typography lesson.

- [ ] **Step 5:** Merge Phase 4 PR after visual verification passes.

---

## Phase 5 — Release (5 tasks, 1 PR)

> **PR boundary:** Phase 5 ships as the v1.4.0 release PR. Requires all of Phase 1-4 merged to main and one production publish (the next 06:30 BDT auto-fire) succeeded against main.

> Before starting: `git switch main && git pull --ff-only && git switch -c release/v1.4.0`

### Task 5.1: Verify one production publish has succeeded against main

**Files:** none

- [ ] **Step 1: Wait for the next 06:30 BDT auto-fire after all Phase 1-4 PRs merged.**

- [ ] **Step 2: SSH to Hetzner and inspect the publish log**:

```bash
ssh adnan@<hetzner> "tail -100 ~/the-brief/logs/brief-systemd.log | grep -E 'chart_read|history_facts|verdict'"
```

- [ ] **Step 3: Check the live site** — load `https://thebrief.clauding-lab.com/` and confirm:
  - Macro section shows 8 metrics
  - Macro section shows the CPI trend chart
  - Every chart-bearing section shows chart_read prose under the chart
  - Cover.sub includes a historical anchor (best-effort — non-zero occurrence in first week)

- [ ] **Step 4:** If anything is broken — STOP and file a bug. Do NOT cut v1.4.0 until production is healthy.

### Task 5.2: Add CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add the v1.4.0 section** above the existing `[1.3.2]` entry:

```markdown
## [1.4.0] — 2026-XX-XX

### Added
- **Historical anchors compute layer** (`brief/history_anchors.py`) — 5 cadence-aware primitives (`last_lower_than`, `last_higher_than`, `pct_change_since`, `rolling_extremes`, `first_cross_since`) that produce `HistoryFact` instances with pre-formatted parens phrases. Reads `metric_history` for daily/weekly and `metric_history_monthly` for monthly long-horizon.
- **`Section.chart_read` field** — structured `{signal, context, implication}` rendered as three short paragraphs in existing `.tb-analysis` styling under each chart card. No new CSS, no new component.
- **8 banker-essential monthly metrics in macro section** — CPI 12m-avg, CPI food, CPI non-food, real policy rate, REER, private credit YoY, M2 YoY, import cover. Pulled from `metric_history_monthly`.
- **CPI 24-month trend chart in macro section** — new `chartConfigs.cpiTrend` config rendering three lines (headline, food, non-food).
- **6 new validators** — `validate_no_banal_language`, `validate_chart_read_temporal_anchor`, `validate_chart_read_implication_quality`, `validate_chart_read_length`, `validate_history_claim_has_reference`, `validate_abbreviation_policy`.
- **Banker vocabulary tiers section in `Master.md`** — Tier 1 (bare use), Tier 2 (expand on first use per section), Tier 3 (always expand or rephrase).

### Changed
- **Editor prompt** (`editor_v6.txt` + `editor_v6_friday.txt`) — banker-grade specificity contract, history_facts weaving rules (use `phrase` verbatim including parens), abbreviation tier policy, macro section 8-metric override.
- **Sub-editor prompt** (`subeditor_v6.txt`) — 7 new checklist items (specificity, temporal anchor, history claim audit, reference preservation, banal language, abbreviation policy, web search if available).
- **`Cover.sub`** — packs historical anchors verbatim when a `since_lower / since_higher / first_cross_since` HistoryFact exists for the cover metric.
- **`MetricHistoryClient`** — extended with `table` kwarg supporting `metric_history_monthly`.

### Conditional (per Phase 0 outcome)
- **Web search sanity check on historical claims** — if Anthropic SDK supports `web_search` tool with current auth, sub-editor runs up to 3 verifications per brief with 25% materiality threshold. Per-search 5s timeout, total 15s budget, hard fail-open.
```

- [ ] **Step 2: Update package.json version**

```bash
sed -i '' 's/"version": "1.3.2"/"version": "1.4.0"/' package.json
```

- [ ] **Step 3: Update README version badge + footer**

```bash
sed -i '' 's/version-1.3.2/version-1.4.0/' README.md
sed -i '' 's/Current: \*\*v1.3.2\*\*/Current: \*\*v1.4.0\*\*/' README.md
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md package.json README.md
git commit -m "release: v1.4.0 — Banker-Grade Read

Bumps package.json 1.3.2 → 1.4.0, README badge + footer, and adds
CHANGELOG entry."
```

### Task 5.3: Open release PR

**Files:** none

- [ ] **Step 1: Push**

```bash
git push -u origin release/v1.4.0
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --base main --head release/v1.4.0 \
  --title "release: v1.4.0 — Banker-Grade Read" \
  --body "Cuts the v1.4.0 release after Phases 1-4 merged and one production
publish verified.

## What's in v1.4.0

- Historical anchors compute layer + macro section enrichment (8 monthly
  metrics + CPI 24-month trend chart)
- Banker-grade specificity in the editor prompt + 7 new sub-editor checks
- ChartRead under every chart card (three prose paragraphs in existing
  .tb-analysis styling)
- Banker vocabulary tier policy in Master.md
- 6 new rule-based validators
- Web search sanity check (conditional on Phase 0 outcome)

## Release flow (per AGENTS.md landmine #11)

1. Squash-merge this PR
2. \`git tag -a v1.4.0 <merge_hash> -m \"...\"\` + \`git push origin v1.4.0\`
3. \`gh release create v1.4.0 --title \"v1.4.0 — Banker-Grade Read\" --notes-file <FILE>\`
4. Verify Latest flag stays on v1.4.0 (GH may auto-bump; \`gh release edit v1.4.0 --latest\` if needed)
5. Append v1.4.0 entry to AGENT_LEARNINGS.md with any incidents from shipping

## Test plan
- [x] package.json + README + CHANGELOG all show 1.4.0
- [ ] Reviewer eyeballs CHANGELOG entry"
```

- [ ] **Step 3: Squash-merge**

```bash
gh pr merge <PR#> --squash --delete-branch
```

### Task 5.4: Tag + publish GH release

**Files:** none

- [ ] **Step 1: Sync main**

```bash
git switch main
git pull --ff-only
```

- [ ] **Step 2: Capture the merge commit hash**

```bash
RELEASE_COMMIT=$(git log -1 --format="%H")
echo "Release commit: $RELEASE_COMMIT"
```

- [ ] **Step 3: Create annotated tag**

```bash
git tag -a v1.4.0 $RELEASE_COMMIT -m "v1.4.0 — Banker-Grade Read

Historical anchors compute layer + macro section enrichment with 8
banker-essential monthly metrics and a new CPI 24-month trend chart.
Banker-grade specificity contract in the editor prompt with 7 new
sub-editor checks. ChartRead prose under every chart card. Banker
vocabulary tier policy in Master.md.

Six new rule-based validators enforce: no banal language, ChartRead
temporal anchor, implication quality, length caps, history reference
preservation, abbreviation policy.

Web search sanity check shipped only if Phase 0 Anthropic SDK
verification was GREEN.

No code regression. Backward-compatible — sections without chart_read
render as before; cover.sub may or may not include a historical anchor.

Spec: docs/superpowers/specs/2026-05-27-banker-grade-read-design.md
Plan: docs/superpowers/plans/2026-05-27-banker-grade-read.md
PRs: Phase 0 (verifications), Phase 1 (compute), Phase 2 (validators),
     Phase 3 (editor+macro), Phase 4 (ChartRead), Phase 5 (this release)"
```

- [ ] **Step 4: Push tag**

```bash
git push origin v1.4.0
```

- [ ] **Step 5: Publish GH release**

```bash
gh release create v1.4.0 \
  --title "v1.4.0 — Banker-Grade Read" \
  --notes "$(cat <<'EOF'
## v1.4.0 — Banker-Grade Read

Closes the depth gap surfaced in the 2026-05-27 brainstorm: existing readers said they wanted more analytical depth — interpretation, implications, historical context — not more raw data.

### Highlights

- **Macro section, transformed.** 8 banker-essential monthly metrics (CPI 12m-avg, food/non-food, real policy rate, REER, private credit YoY, M2 YoY, import cover) from `metric_history_monthly` + a new CPI 24-month trend chart.
- **Every chart now has a Chart Read.** Three short paragraphs (signal / context / implication) sitting directly under each chart card in existing `.tb-analysis` styling. No new CSS — minimal visual diff.
- **Historical anchors that auditably cite their data.** "Lowest 12-month CPI since Sep 2021 (4.8% then)" — the reference value sits in parens, pre-formatted by Python, never invented by the model.
- **Banker-grade specificity contract.** Editor prompt + 7 sub-editor checks enforce: time-anchored claims, implications over restatement, no AI-tell banality, abbreviation expansion per Tier-2 policy.

### Added

- `brief/history_anchors.py` — compute layer with 5 cadence-aware primitives.
- `Section.chart_read: {signal, context, implication}` — new structured field on every chart-bearing section.
- `cpiTrend` chart config + macro section enrichment.
- `Master.md` banker vocabulary tiers (Tier 1 bare / Tier 2 expand-on-first / Tier 3 rephrase).
- 6 new validators in `brief/claude/validators.py`.

### Changed

- Editor prompt: banker-grade specificity contract, history_facts weaving rules, macro 8-metric override.
- Sub-editor prompt: 7 new checklist items + (conditional) web search sanity check.
- `Cover.sub`: packs historical anchors verbatim when notable.

### Full changelog

See the [v1.4.0 entry in CHANGELOG.md](https://github.com/clauding-lab/the-brief/blob/main/CHANGELOG.md#140--2026-XX-XX).
EOF
)"
```

- [ ] **Step 6: Verify Latest flag**

```bash
gh release list --limit 4
# If v1.4.0 isn't marked Latest:
gh release edit v1.4.0 --latest
```

### Task 5.5: Append v1.4.0 entry to AGENT_LEARNINGS.md

**Files:**
- Modify: `AGENT_LEARNINGS.md`

- [ ] **Step 1: Add an entry at the top of the "Entries" section** capturing any incidents from the v1.4.0 shipping process. If shipping was clean, the entry is brief and notes the smooth process:

```markdown
## 2026-XX-XX — v1.4.0 | Banker-Grade Read release

**Trigger:** Five-phase release per the v1.4.0 plan.

**What went well:** [Capture specifics — e.g., "all 5 PRs merged on schedule, dry-run smoke catches X validator failure before merge"]

**What went wrong:** [Capture specifics — e.g., "Phase 0 found web_search unsupported, scoped out cleanly", or "ChartRead rendered too densely on mobile per v1.2.1 lesson — patched in v1.4.1"]

**Lesson:** [Generalizable rule, if any]

**Prevention:** [Carry forward into AGENTS.md landmines if stable]

**Cross-references:** PRs #X-#Y, spec at docs/superpowers/specs/2026-05-27-banker-grade-read-design.md
```

- [ ] **Step 2: Commit + push directly to main** (small docs chore, no PR needed):

```bash
git switch main
git pull --ff-only
git add AGENT_LEARNINGS.md
git commit -m "docs(learnings): add v1.4.0 release entry"
git push origin main
```

- [ ] **Step 3:** Done. v1.4.0 is shipped.

---

## Self-Review

After writing the plan above, here's the spec-coverage check:

| Spec section | Plan coverage |
|---|---|
| §3.1 Historical anchors compute layer | Phase 1, Tasks 1.1-1.8 |
| §3.2 Editor prompt upgrade | Phase 3, Tasks 3.4-3.5 |
| §3.3 Abbreviation tier policy | Phase 2, Task 2.8 (Master.md) + Phase 3, Task 3.4 (editor prompt) |
| §3.4 Sub-editor checks (7 items) | Phase 2, Task 2.7 |
| §3.5 Validators (6 functions + constants) | Phase 2, Tasks 2.1-2.6 |
| §3.6 Macro section enrichment | Phase 3, Tasks 3.2, 3.6, 3.7 |
| §3.7 ChartRead schema + render | Phase 4, Tasks 4.1-4.3 |
| §3.8 Failure-mode handling | Distributed: web search budget in 2.7, fail-open behavior, optional chart_read |

**Placeholder scan:** no "TBD" or "TODO". A few "implementation may need to look at actual current call site" notes appear in Task 2.7 and 3.3 — these are appropriately scoped guidance, not placeholders.

**Type consistency:** `HistoryFact` is consistently spelled and structured everywhere it appears (Phase 1 dataclass → Phase 3 editor input dict → Phase 2 validator consumption). `ChartRead` is consistently `{signal, context, implication}` everywhere.

**One gap caught:** the plan doesn't explicitly task an `__init__.py` re-export of `HistoryFact` from `brief/history_anchors.py`. The implementer should add the export in Task 1.2.

## Out-of-scope items for future phases

- ChartRead + history for Long View `bar-chart` block kind → v1.4.1
- Story-recurrence history → v1.4.x
- "Next Read" forward-looking Cover anchor → after v1.4.0
- Additional macro charts (REER, real policy rate, credit growth) → v1.5.0 "Macro Depth"
- Banking Pulse section (NPL + CRAR quarterly + call money rate daily) → v1.6.0
- Desk-specific framing → v2.0
- API / Brief Numbers subscriber perk → v2.x

---

**End of v1.4.0 implementation plan.**
