-- migrations/0003_section_freshness.sql
-- Adds per-section freshness annotation for the dead-section-collapse SPA feature
-- (Phase D.2). Nullable so historical issues stay valid.

ALTER TABLE sections ADD COLUMN freshness TEXT
  CHECK (freshness IS NULL OR freshness IN ('fresh','warning','stale','unavailable','warming_up'));

COMMENT ON COLUMN sections.freshness IS
  'V5-derived per-section freshness label: fresh|warning|stale|unavailable|warming_up. NULL on pre-D.2 issues.';
