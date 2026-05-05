-- migrations/0002_v6_freshness.sql
-- Adds freshness annotation columns for V6 fresh-brief plan (V1).
-- All new columns nullable; populated post-LLM by builders in pipeline_v6.

ALTER TABLE metrics ADD COLUMN held_from DATE;
ALTER TABLE metrics ADD COLUMN next_print TEXT;

ALTER TABLE news ADD COLUMN held_from DATE;

ALTER TABLE briefs ADD COLUMN lens TEXT;
ALTER TABLE briefs ADD COLUMN frame TEXT;

COMMENT ON COLUMN metrics.held_from IS
  'Date this exact metric value first appeared (held-over from this issue). NULL = fresh today.';
COMMENT ON COLUMN metrics.next_print IS
  'Free-text label for next expected publication, e.g. "Q3 2026 (≈ Jul 2026)".';
COMMENT ON COLUMN news.held_from IS
  'Date this exact headline first appeared in a brief. NULL = fresh today. Rare — most repeats are filtered upstream.';
COMMENT ON COLUMN briefs.lens IS
  'Today''s editorial lens (banking|fx|dse|tbond|macro|iran|weekly_wrap). Drives hero section + cover metric.';
COMMENT ON COLUMN briefs.frame IS
  'Today''s editorial frame (sovereign-debt|FX-runway|credit-cycle|rates-curve|external-shock|weekly-wrap). Drives todays_call prose structure.';
