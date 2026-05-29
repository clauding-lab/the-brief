-- migrations/0004_section_chart_read.sql
-- Adds the v1.4.0 banker-grade ChartReadV6 structured field to sections.
--
-- v1.4.0 (PR #95, 2026-05-27 14:28 UTC) shipped Section.chart_read in the
-- Pydantic schema and the SPA component, but the matching DB migration was
-- never written. The first publish under v1.4.0 (Thursday 2026-05-28
-- 00:30 UTC) failed with PGRST204:
--
--   "Could not find the 'chart_read' column of 'sections' in the schema cache"
--
-- The brief row inserted before the sections call, so Brief #118 is
-- orphaned (status=published but 0 sections / 0 metrics / 0 news / 0
-- chart_series). Friday's publish was separately blocked by an Anthropic
-- editor timeout AND would have hit this same schema error on retry.
--
-- Shape: structured {signal, context, implication} JSON per the ChartReadV6
-- Pydantic model in brief/v6_schema.py. Nullable so historical issues stay
-- valid (no backfill needed; v1.3.x and earlier issues never had this).

ALTER TABLE public.sections
  ADD COLUMN IF NOT EXISTS chart_read jsonb;

COMMENT ON COLUMN public.sections.chart_read IS
  'v1.4.0 banker-grade Chart Read: structured {signal, context, implication} JSON rendered as the "Chart read" eyebrow under each chart card. NULL for pre-v1.4.0 issues.';

-- Notify PostgREST so the new column is visible to the schema cache
-- without restarting the postgrest worker.
NOTIFY pgrst, 'reload schema';
