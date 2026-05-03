# Brief Part 2 — Shadow Observations

Log one entry per day during shadow soak. A run counts as **clean** iff every box is ticked. Cutover requires **3 consecutive clean days**.

---

## 2026-04-26 (Sun)

- Shadow branch: `shadow/2026-04-26` — commit `_____`
- GHA run: actions run `_____`
- [ ] Both pipelines produced an `index.html`.
- [ ] `jq '.status' shadow/run_report.json` == `"ok"`.
- [ ] All 3 original Claude calls (`headlines_curation`, `exec_signals`, `bankerread`) `status == "ok"`.
- [ ] Both new Claude calls (`risk_map_layout`, `todays_call`) `status == "ok"` or cleanly fell back.
- [ ] `degraded_sections` — `[]` OR documented below.
- [ ] `total_cost_usd` ≤ 5.00.
- [ ] Visual diff (eyeball GHA's `index.html` vs shadow's): V4 layout matches the decisions doc. Today's Call aside present. Risk map renders 12 dots. No missing sections. No sections showing raw JSON.
- [ ] Email digest (`email.txt`) — subject-line text plausible, 5 headlines present, links non-empty.

**Drift notes:** _____

**Decision:** [ ] clean  [ ] dirty → reason _____

---

## 2026-04-27 (Mon)

- Shadow branch: `shadow/2026-04-27` — commit `_____`
- GHA run: actions run `_____`
- [ ] Both pipelines produced an `index.html`.
- [ ] `jq '.status' shadow/run_report.json` == `"ok"`.
- [ ] All 3 original Claude calls (`headlines_curation`, `exec_signals`, `bankerread`) `status == "ok"`.
- [ ] Both new Claude calls (`risk_map_layout`, `todays_call`) `status == "ok"` or cleanly fell back.
- [ ] `degraded_sections` — `[]` OR documented below.
- [ ] `total_cost_usd` ≤ 5.00.
- [ ] Visual diff (eyeball GHA's `index.html` vs shadow's): V4 layout matches the decisions doc. Today's Call aside present. Risk map renders 12 dots. No missing sections. No sections showing raw JSON.
- [ ] Email digest (`email.txt`) — subject-line text plausible, 5 headlines present, links non-empty.

**Drift notes:** _____

**Decision:** [ ] clean  [ ] dirty → reason _____

---

## 2026-04-28 (Tue)

- Shadow branch: `shadow/2026-04-28` — commit `_____`
- GHA run: actions run `_____`
- [ ] Both pipelines produced an `index.html`.
- [ ] `jq '.status' shadow/run_report.json` == `"ok"`.
- [ ] All 3 original Claude calls (`headlines_curation`, `exec_signals`, `bankerread`) `status == "ok"`.
- [ ] Both new Claude calls (`risk_map_layout`, `todays_call`) `status == "ok"` or cleanly fell back.
- [ ] `degraded_sections` — `[]` OR documented below.
- [ ] `total_cost_usd` ≤ 5.00.
- [ ] Visual diff (eyeball GHA's `index.html` vs shadow's): V4 layout matches the decisions doc. Today's Call aside present. Risk map renders 12 dots. No missing sections. No sections showing raw JSON.
- [ ] Email digest (`email.txt`) — subject-line text plausible, 5 headlines present, links non-empty.

**Drift notes:** _____

**Decision:** [ ] clean  [ ] dirty → reason _____

---

## 2026-04-29 (Wed)

- Shadow branch: `shadow/2026-04-29` — commit `_____`
- GHA run: actions run `_____`
- [ ] Both pipelines produced an `index.html`.
- [ ] `jq '.status' shadow/run_report.json` == `"ok"`.
- [ ] All 3 original Claude calls (`headlines_curation`, `exec_signals`, `bankerread`) `status == "ok"`.
- [ ] Both new Claude calls (`risk_map_layout`, `todays_call`) `status == "ok"` or cleanly fell back.
- [ ] `degraded_sections` — `[]` OR documented below.
- [ ] `total_cost_usd` ≤ 5.00.
- [ ] Visual diff (eyeball GHA's `index.html` vs shadow's): V4 layout matches the decisions doc. Today's Call aside present. Risk map renders 12 dots. No missing sections. No sections showing raw JSON.
- [ ] Email digest (`email.txt`) — subject-line text plausible, 5 headlines present, links non-empty.

**Drift notes:** _____

**Decision:** [ ] clean  [ ] dirty → reason _____

---

## 2026-04-30 (Thu)

- Shadow branch: `shadow/2026-04-30` — commit `_____`
- GHA run: actions run `_____`
- [ ] Both pipelines produced an `index.html`.
- [ ] `jq '.status' shadow/run_report.json` == `"ok"`.
- [ ] All 3 original Claude calls (`headlines_curation`, `exec_signals`, `bankerread`) `status == "ok"`.
- [ ] Both new Claude calls (`risk_map_layout`, `todays_call`) `status == "ok"` or cleanly fell back.
- [ ] `degraded_sections` — `[]` OR documented below.
- [ ] `total_cost_usd` ≤ 5.00.
- [ ] Visual diff (eyeball GHA's `index.html` vs shadow's): V4 layout matches the decisions doc. Today's Call aside present. Risk map renders 12 dots. No missing sections. No sections showing raw JSON.
- [ ] Email digest (`email.txt`) — subject-line text plausible, 5 headlines present, links non-empty.

**Drift notes:** _____

**Decision:** [ ] clean  [ ] dirty → reason _____

---

## Cutover eligibility

- [ ] 3 consecutive clean days (≥ 2026-04-XX)
- [ ] No rollbacks during the soak window
- [ ] No ad-hoc manual pipeline edits that would invalidate the observations

Once eligible: proceed to `docs/ops/part2-cutover-runbook.md`.
