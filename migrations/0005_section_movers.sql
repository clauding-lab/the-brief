-- migrations/0005_section_movers.sql
-- Adds the F4 DS30 Movers structured field to sections.
--
-- F4 renders a ranked top-5-gainers + top-5-losers block in §dse, computed at
-- publish time from per-ticker dse_close_* rows. The list is stored as a JSONB
-- array of {ticker, price, return_pct} per the MoverRowV6 Pydantic model in
-- brief/v6_schema.py.
--
-- MANDATORY before the first publish under F4 code: the publisher serializes
-- every non-excluded SectionV6 field onto the sections row, so it will POST
-- `movers` (null when the freshness gate hides it). Without this column the
-- insert fails PGRST204 and orphans the brief — exactly the v1.4.0 chart_read
-- incident (Brief #118, see AGENT_LEARNINGS.md 2026-05-29). Nullable so
-- historical issues stay valid (no backfill).

ALTER TABLE public.sections
  ADD COLUMN IF NOT EXISTS movers jsonb;

COMMENT ON COLUMN public.sections.movers IS
  'F4 DS30 Movers: JSONB array of {ticker, price, return_pct} (top-5 gainers then top-5 losers, 1-month return) rendered full-width below the §dse chart. NULL when the freshness gate hides it or for pre-F4 issues.';

-- Notify PostgREST so the new column is visible without restarting the worker.
NOTIFY pgrst, 'reload schema';
