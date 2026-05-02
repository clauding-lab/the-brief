# The Brief

Daily morning brief for Bangladesh economy + markets. Renders a static
HTML newspaper at ~06:30 BDT every weekday from Supabase data + Claude
narrative prompts, publishes to GitHub Pages.

## Data flow

The Brief is a **read-only consumer** of the EconDelta data layer:

```
   EconDelta @ ExonVPS  ──→  Supabase metric_history  ──→  The Brief @ Hetzner
   (writes daily 06:10        (warm queryable history)     (renders 06:30 BDT,
    BDT)                                                    publishes to GH Pages)
```

**Wanting to add a new metric to the brief?** First add the scraper in
EconDelta. Once the metric_id appears in
[`econdelta/docs/indicator-catalog.md`](https://github.com/clauding-lab/econdelta/blob/feat/v3-expansion/docs/indicator-catalog.md)
the brief reads it via Supabase — no scraper code in this repo.

For consumer semantics (auth, schema, query patterns, NULL handling)
see [`econdelta/docs/data-contract.md`](https://github.com/clauding-lab/econdelta/blob/feat/v3-expansion/docs/data-contract.md).

## Layout

| Path | Purpose |
|------|---------|
| `brief/cli.py` | Entry point — `python -m brief.cli run` |
| `brief/pipeline.py` | Orchestrates section builders + Claude prompts + render |
| `brief/builders/*.py` | Per-section builders (banking, dam, fx, ...). Read-only against `ctx.history` (Supabase) and `ctx.snapshot` (latest.json). |
| `brief/render/v5/` | V5 HTML templates (cream-paper newspaper) |
| `brief/claude/` | Claude prompts for narrative sections |
| `brief/history.py` | PostgREST client wrapping `metric_history` reads |
| `brief/econdelta.py` | Reader for `data/latest.json` (mirrored from ExonVPS via 5-min rsync) |

## Run

```bash
# Locally (requires env file with SUPABASE_URL + SERVICE_ROLE_KEY)
source .venv/bin/activate
set -a && source /etc/brief.env && set +a
python -m brief.cli run --artifacts-dir /tmp/brief-out
```

## Tests

```bash
pytest -q
```
