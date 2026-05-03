# Brief Part 2 — Migration Audit (7 days post-cutover)

Tick each criterion with evidence. Complete on 2026-05-09 at earliest.

| # | Criterion | Evidence | OK |
|---|---|---|---|
| 1 | Zero GHA runs in the last 7 days | `gh run list -w daily-update.yml --limit 20` → 0 scheduled | [ ] |
| 2 | Zero Anthropic API spend | Anthropic console → last-7-day usage == $0 | [ ] |
| 3 | Daily ship Sun–Fri | 5–6 commits on `main` with brief artifacts in the last 7 days | [ ] |
| 4 | No fabricated facts (10 random numeric spot checks) | Traced 10 values → all cite source + as_of | [ ] |
| 5 | Graceful degradation observed ≥1× | `jq -r 'select(.degraded_sections | length > 0) | .today' run_report.json` → ≥1 day | [ ] |
| 6 | Run duration < 15m (p95 over 7 days) | `jq .duration_s run_report.json` → max ≤ 900 | [ ] |
| 7 | Claude validators pass 100% | No `status: invalid` in any `call_reports` over 7 days | [ ] |
| 8 | Rollback rehearsed once | `BRIEF_DRY_RUN=1` + GHA re-enable + reversion recorded in dated note | [ ] |

**Migration complete when all 8 boxes are ticked.**
