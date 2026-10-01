-- migrations/0006_publish_brief_atomic.sql
-- R3: publish a whole edition in ONE database transaction.
--
-- Plain English: today the publisher deletes the day's issue and then re-adds
-- it piece by piece over many separate web requests. A crash in the middle
-- leaves the day's issue gone. This migration adds one database function that
-- does the whole replacement inside a single transaction: either every row of
-- the new edition lands together, or nothing changes and the previous complete
-- edition stays exactly as it was.
--
-- What it contains (and nothing else — no new tables, columns or constraints):
--   1. Preconditions: fail with a clear message if the six publication tables
--      drifted from the captured production definitions (26 Sep 2026 BDT).
--   2. public.publish_brief_atomic(p_expected_issue_no, p_expected_brief_date,
--      p_payload) — VOLATILE, SECURITY INVOKER, fixed empty search_path.
--   3. EXECUTE on it for service_role only (revoked from PUBLIC, anon,
--      authenticated). Owner decision (b), 26 Sep 2026: revoke the unused
--      write-type table privileges (INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER,
--      REFERENCES, MAINTAIN) on the six tables from anon and authenticated.
--      SELECT, the read policies and get_latest_brief (body and ACL) are
--      unchanged.
--   4. Postconditions proving the resulting privileges, then a PostgREST
--      schema-cache reload (NOTIFY pgrst, 'reload schema').
--
-- Apply path (AGENTS.md landmine 18): the owner applies this file once through
-- the Supabase SQL editor BEFORE the Python that calls the function is merged.
-- It needs PostgreSQL 17 (MAINTAIN privilege). Safe to re-run: the function is
-- CREATE OR REPLACE and every grant statement is idempotent.
--
-- Future schema changes: the function accepts only payload objects with EXACTLY
-- the keys listed in c_spec. A new column-mapped payload field therefore needs a
-- CREATE OR REPLACE of this function in the SAME migration as its ALTER TABLE
-- (landmine 18's ADD COLUMN alone makes every publication hold with
-- invalid_payload). See the COMMENT ON FUNCTION below.

BEGIN;

-- ─── 1. Preconditions ────────────────────────────────────────────────────
DO $pre$
DECLARE
  v_expected_columns constant text[] := ARRAY[
    'briefs.brief_date date not null',
    'briefs.cover_metric jsonb null',
    'briefs.created_at timestamp with time zone null',
    'briefs.frame text null',
    'briefs.id uuid not null',
    'briefs.issue_no integer not null',
    'briefs.lens text null',
    'briefs.published_at timestamp with time zone null',
    'briefs.read_minutes integer null',
    'briefs.status text not null',
    'briefs.todays_call text null',
    'briefs.volume integer not null',
    'chart_notes.detail text null',
    'chart_notes.id uuid not null',
    'chart_notes.label text null',
    'chart_notes.section_id uuid null',
    'chart_notes.series_key text not null',
    'chart_notes.ts date not null',
    'chart_series.id uuid not null',
    'chart_series.section_id uuid null',
    'chart_series.series_key text not null',
    'chart_series.ts date not null',
    'chart_series.value numeric not null',
    'metrics.changed boolean null',
    'metrics.delta text null',
    'metrics.delta_pct text null',
    'metrics.held_from date null',
    'metrics.id uuid not null',
    'metrics.is_snapshot boolean null',
    'metrics.label text not null',
    'metrics.next_print text null',
    'metrics.ord integer null',
    'metrics.section_id uuid null',
    'metrics.spark numeric[] null',
    'metrics.sub text null',
    'metrics.tone text null',
    'metrics.value text not null',
    'metrics.weight integer null',
    'news.changed boolean null',
    'news.detail text null',
    'news.headline text not null',
    'news.held_from date null',
    'news.id uuid not null',
    'news.ord integer null',
    'news.published_at timestamp with time zone null',
    'news.section_id uuid null',
    'news.source text null',
    'news.source_url text null',
    'news.tone text null',
    'sections.analysis text null',
    'sections.banker_read jsonb null',
    'sections.brief_id uuid null',
    'sections.chart_read jsonb null',
    'sections.freshness text null',
    'sections.group_key text not null',
    'sections.id uuid not null',
    'sections.movers jsonb null',
    'sections.ord integer not null',
    'sections.slug text not null',
    'sections.summary_pills jsonb null',
    'sections.title text not null',
    'sections.tldr text null',
    'sections.verdict text null',
    'sections.verdict_tone text null',
    'sections.weight integer null'
  ];
  v_actual_columns text[];
  v_table text;
  v_rec record;
BEGIN
  IF pg_catalog.current_setting('server_version_num')::integer < 170000 THEN
    RAISE EXCEPTION '0006 precondition: PostgreSQL 17 or newer is required (MAINTAIN privilege); found %',
      pg_catalog.current_setting('server_version');
  END IF;

  FOREACH v_table IN ARRAY ARRAY['briefs', 'sections', 'metrics', 'news', 'chart_series', 'chart_notes'] LOOP
    IF pg_catalog.to_regclass('public.' || v_table) IS NULL THEN
      RAISE EXCEPTION '0006 precondition: table public.% is missing', v_table;
    END IF;
  END LOOP;

  SELECT pg_catalog.array_agg(col.d ORDER BY col.d) INTO v_actual_columns
    FROM (SELECT pg_catalog.format('%s.%s %s %s', c.relname, a.attname,
                   pg_catalog.format_type(a.atttypid, a.atttypmod),
                   CASE WHEN a.attnotnull THEN 'not null' ELSE 'null' END) AS d
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
           WHERE c.relnamespace = 'public'::pg_catalog.regnamespace
             AND c.relname IN ('briefs', 'sections', 'metrics', 'news', 'chart_series', 'chart_notes')
             AND a.attnum > 0 AND NOT a.attisdropped) AS col;
  IF v_actual_columns IS DISTINCT FROM
     (SELECT pg_catalog.array_agg(x ORDER BY x) FROM pg_catalog.unnest(v_expected_columns) x) THEN
    RAISE EXCEPTION '0006 precondition: publication table columns drifted from the 26 Sep 2026 capture. Unexpected: %; missing: %',
      (SELECT pg_catalog.array_agg(x) FROM pg_catalog.unnest(v_actual_columns) x WHERE x <> ALL (v_expected_columns)),
      (SELECT pg_catalog.array_agg(x) FROM pg_catalog.unnest(v_expected_columns) x WHERE x <> ALL (v_actual_columns));
  END IF;

  -- Primary keys on id, generated by gen_random_uuid() (the function never supplies ids).
  FOR v_rec IN
    SELECT t.relname,
           EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k
                    WHERE k.conrelid = t.oid AND k.contype = 'p'
                      AND k.conkey = ARRAY[(SELECT a.attnum FROM pg_catalog.pg_attribute a
                                             WHERE a.attrelid = t.oid AND a.attname = 'id')]) AS has_pk,
           (SELECT pg_catalog.pg_get_expr(d.adbin, d.adrelid) FROM pg_catalog.pg_attrdef d
             JOIN pg_catalog.pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
            WHERE d.adrelid = t.oid AND a.attname = 'id') AS id_default
      FROM pg_catalog.pg_class t
     WHERE t.relnamespace = 'public'::pg_catalog.regnamespace
       AND t.relname IN ('briefs', 'sections', 'metrics', 'news', 'chart_series', 'chart_notes')
  LOOP
    IF NOT v_rec.has_pk OR v_rec.id_default IS DISTINCT FROM 'gen_random_uuid()' THEN
      RAISE EXCEPTION '0006 precondition: public.% must have PRIMARY KEY (id) with DEFAULT gen_random_uuid() (found pk=%, default=%)',
        v_rec.relname, v_rec.has_pk, v_rec.id_default;
    END IF;
  END LOOP;

  -- Uniqueness the function relies on: issue numbers, section slugs per brief, chart points.
  FOR v_rec IN
    SELECT u.tbl, u.cols
      FROM (VALUES ('briefs', ARRAY['issue_no']),
                   ('sections', ARRAY['brief_id', 'slug']),
                   ('chart_series', ARRAY['section_id', 'series_key', 'ts'])) AS u(tbl, cols)
     WHERE NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_constraint k
        WHERE k.conrelid = ('public.' || u.tbl)::pg_catalog.regclass AND k.contype = 'u'
          AND (SELECT pg_catalog.array_agg(a.attname::text ORDER BY o.n)
                 FROM pg_catalog.unnest(k.conkey) WITH ORDINALITY o(attnum, n)
                 JOIN pg_catalog.pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = o.attnum) = u.cols)
  LOOP
    RAISE EXCEPTION '0006 precondition: UNIQUE (%) on public.% is missing', pg_catalog.array_to_string(v_rec.cols, ', '), v_rec.tbl;
  END LOOP;

  -- Child replacement deletes sections only; every child row must cascade from its parent.
  FOR v_rec IN
    SELECT f.child, f.col, f.parent
      FROM (VALUES ('sections', 'brief_id', 'briefs'),
                   ('metrics', 'section_id', 'sections'),
                   ('news', 'section_id', 'sections'),
                   ('chart_series', 'section_id', 'sections'),
                   ('chart_notes', 'section_id', 'sections')) AS f(child, col, parent)
     WHERE NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_constraint k
        WHERE k.conrelid = ('public.' || f.child)::pg_catalog.regclass AND k.contype = 'f'
          AND k.confrelid = ('public.' || f.parent)::pg_catalog.regclass
          AND k.confdeltype = 'c'
          AND k.conkey = ARRAY[(SELECT a.attnum FROM pg_catalog.pg_attribute a
                                 WHERE a.attrelid = k.conrelid AND a.attname = f.col)]
          AND k.confkey = ARRAY[(SELECT a.attnum FROM pg_catalog.pg_attribute a
                                  WHERE a.attrelid = k.confrelid AND a.attname = 'id')])
  LOOP
    RAISE EXCEPTION '0006 precondition: public.%(%) must REFERENCE public.%(id) ON DELETE CASCADE', v_rec.child, v_rec.col, v_rec.parent;
  END LOOP;

  FOREACH v_table IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF pg_catalog.to_regrole(v_table) IS NULL THEN
      RAISE EXCEPTION '0006 precondition: role % is missing', v_table;
    END IF;
  END LOOP;

  -- Exactly one signature may ever exist (no overloads a caller could hit by accident).
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc p
              WHERE p.pronamespace = 'public'::pg_catalog.regnamespace
                AND p.proname = 'publish_brief_atomic'
                AND p.oid IS DISTINCT FROM pg_catalog.to_regprocedure('public.publish_brief_atomic(integer, date, jsonb)')) THEN
    RAISE EXCEPTION '0006 precondition: another public.publish_brief_atomic signature exists; refusing to create an overload';
  END IF;
END
$pre$;

-- ─── 2. The atomic writer ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.publish_brief_atomic(
  p_expected_issue_no integer,
  p_expected_brief_date date,
  p_payload jsonb
) RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = ''
AS $fn$
DECLARE
  -- Transaction advisory lock shared by every compliant publisher: ASCII 'BRIEFPUB'.
  c_lock_key constant bigint := 4778962716474758466;
  -- Exact key sets and JSON types of every column-mapped object (BriefPayloadV6,
  -- model_dump(mode="json")). "integer" = a JSON number with no fractional part.
  -- A new column-mapped field must be added here AND to the INSERT/UPDATE below,
  -- in the same migration as its ALTER TABLE (see the function COMMENT).
  c_spec constant jsonb := '{
    "brief": {"issue_no": ["integer"], "volume": ["integer"], "brief_date": ["string"],
              "read_minutes": ["integer", "null"], "cover_metric": ["object", "null"],
              "todays_call": ["string", "null"], "status": ["string", "null"],
              "lens": ["string", "null"], "frame": ["string", "null"]},
    "section": {"slug": ["string"], "ord": ["integer"], "title": ["string"], "group_key": ["string"],
                "freshness": ["string", "null"], "verdict": ["string", "null"],
                "verdict_tone": ["string", "null"], "banker_read": ["object", "null"],
                "weight": ["integer"], "tldr": ["string", "null"], "summary_pills": ["array"],
                "analysis": ["string", "null"], "chart_read": ["object", "null"],
                "movers": ["array", "null"], "metrics": ["array"], "news": ["array"],
                "series": ["array"], "notes": ["array"]},
    "metrics": {"label": ["string"], "value": ["string"], "sub": ["string", "null"],
                "tone": ["string", "null"], "is_snapshot": ["boolean", "null"],
                "spark": ["array", "null"], "delta": ["string", "null"],
                "delta_pct": ["string", "null"], "changed": ["boolean", "null"],
                "weight": ["integer", "null"], "held_from": ["string", "null"],
                "next_print": ["string", "null"]},
    "news": {"headline": ["string"], "detail": ["string", "null"], "source": ["string", "null"],
             "source_url": ["string", "null"], "published_at": ["string", "null"],
             "tone": ["string", "null"], "changed": ["boolean", "null"],
             "held_from": ["string", "null"]},
    "series": {"key": ["string", "null"], "ts": ["string"], "value": ["number"]},
    "notes": {"series_key": ["string"], "ts": ["string"], "label": ["string"],
              "detail": ["string", "null"]}
  }';
  v_brief jsonb;
  v_sections jsonb;
  v_bad text;
  v_count integer;
  v_max_issue integer;
  v_target record;
  v_brief_id uuid;
  v_created boolean;
  v_section record;
  v_section_id uuid;
  v_rows integer;
  v_published_at timestamptz;
BEGIN
  -- ── Arguments and transaction mode ─────────────────────────────────────
  IF p_expected_issue_no IS NULL OR p_expected_brief_date IS NULL OR p_payload IS NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: all three arguments are required' USING HINT = 'invalid_payload';
  END IF;
  IF p_expected_issue_no < 1 THEN
    RAISE EXCEPTION 'publish_brief_atomic: expected issue number must be positive (got %)', p_expected_issue_no
      USING HINT = 'invalid_payload';
  END IF;
  -- Each statement below must see rows committed by a writer that held the lock before us.
  IF pg_catalog.current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'publish_brief_atomic: requires READ COMMITTED isolation (got %)',
      pg_catalog.current_setting('transaction_isolation') USING HINT = 'unsupported_isolation';
  END IF;

  -- ── Payload structure (state-independent; checked before taking the lock) ──
  IF pg_catalog.jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload must be a JSON object' USING HINT = 'invalid_payload';
  END IF;
  IF (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(p_payload) k)
     IS DISTINCT FROM ARRAY['brief', 'sections'] THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload must have exactly the keys brief and sections'
      USING HINT = 'invalid_payload';
  END IF;
  v_brief := p_payload -> 'brief';
  v_sections := p_payload -> 'sections';
  IF pg_catalog.jsonb_typeof(v_brief) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload.brief must be an object' USING HINT = 'invalid_payload';
  END IF;
  IF pg_catalog.jsonb_typeof(v_sections) IS DISTINCT FROM 'array' OR pg_catalog.jsonb_array_length(v_sections) < 1 THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload.sections must be a non-empty array' USING HINT = 'invalid_payload';
  END IF;
  SELECT pg_catalog.format('sections[%s]', s.i - 1) INTO v_bad
    FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i)
   WHERE pg_catalog.jsonb_typeof(s.o) <> 'object' ORDER BY s.i LIMIT 1;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: % must be an object', v_bad USING HINT = 'invalid_payload';
  END IF;
  SELECT pg_catalog.format('sections[%s].%s', s.i - 1, f.fam) INTO v_bad
    FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i)
   CROSS JOIN (VALUES ('metrics'), ('news'), ('series'), ('notes')) f(fam)
   WHERE pg_catalog.jsonb_typeof(s.o -> f.fam) IS DISTINCT FROM 'array' ORDER BY s.i, f.fam LIMIT 1;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: % must be an array (present, not null)', v_bad USING HINT = 'invalid_payload';
  END IF;
  SELECT pg_catalog.format('sections[%s].%s[%s]', s.i - 1, f.fam, e.i - 1) INTO v_bad
    FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i)
   CROSS JOIN (VALUES ('metrics'), ('news'), ('series'), ('notes')) f(fam)
   CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(s.o -> f.fam) WITH ORDINALITY e(o, i)
   WHERE pg_catalog.jsonb_typeof(e.o) <> 'object' ORDER BY s.i, f.fam, e.i LIMIT 1;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: % must be an object', v_bad USING HINT = 'invalid_payload';
  END IF;

  -- Every column-mapped object: exact key set (unknown control fields and ids are refused),
  -- then the JSON type of every value.
  WITH spec AS MATERIALIZED (
    SELECT f.key AS fam, f.value AS types,
           (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(f.value) k) AS keys
      FROM pg_catalog.jsonb_each(c_spec) f
  ), secs AS MATERIALIZED (
    SELECT s.o, s.i FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i)
  ), objs AS MATERIALIZED (
    SELECT 'brief'::text AS fam, 'brief'::text AS path, v_brief AS o, 0::bigint AS a, 0::bigint AS b
    UNION ALL
    SELECT 'section', pg_catalog.format('sections[%s]', secs.i - 1), secs.o, secs.i, 0 FROM secs
    UNION ALL
    SELECT f.fam, pg_catalog.format('sections[%s].%s[%s]', secs.i - 1, f.fam, e.i - 1), e.o, secs.i, e.i
      FROM secs CROSS JOIN (VALUES ('metrics'), ('news'), ('series'), ('notes')) f(fam)
     CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(secs.o -> f.fam) WITH ORDINALITY e(o, i)
  ), okeys AS (
    SELECT objs.fam, objs.path, objs.a, objs.b,
           (SELECT pg_catalog.array_agg(k ORDER BY k) FROM pg_catalog.jsonb_object_keys(objs.o) k) AS keys
      FROM objs
  ), bad AS (
    SELECT okeys.path || ' has keys ' || pg_catalog.array_to_string(okeys.keys, ',')
           || '; expected exactly ' || pg_catalog.array_to_string(spec.keys, ',') AS msg,
           1 AS rank, okeys.a, okeys.b
      FROM okeys JOIN spec ON spec.fam = okeys.fam
     WHERE okeys.keys IS DISTINCT FROM spec.keys
    UNION ALL
    SELECT objs.path || '.' || e.k || ' must be ' || pg_catalog.array_to_string(
             ARRAY(SELECT pg_catalog.jsonb_array_elements_text(spec.types -> e.k)), ' or ')
           || ' (got ' || pg_catalog.jsonb_typeof(e.v) || ')',
           2, objs.a, objs.b
      FROM objs JOIN spec ON spec.fam = objs.fam
     CROSS JOIN LATERAL pg_catalog.jsonb_each(objs.o) e(k, v)
     WHERE spec.types ? e.k
       AND NOT (CASE
                  WHEN (spec.types -> e.k) ? pg_catalog.jsonb_typeof(e.v) THEN true
                  WHEN (spec.types -> e.k) ? 'integer' AND pg_catalog.jsonb_typeof(e.v) = 'number'
                    THEN (e.v::text)::numeric = pg_catalog.trunc((e.v::text)::numeric)
                  ELSE false
                END)
  )
  SELECT bad.msg INTO v_bad FROM bad ORDER BY bad.rank, bad.a, bad.b, bad.msg LIMIT 1;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: %', v_bad USING HINT = 'invalid_payload';
  END IF;

  -- Stored-verbatim JSON containers: element shapes only (inner keys stay Python's contract).
  SELECT pg_catalog.format('sections[%s].%s[%s]', s.i - 1, f.fam, e.i - 1) INTO v_bad
    FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i)
   CROSS JOIN (VALUES ('summary_pills'), ('movers')) f(fam)
   CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
     CASE WHEN pg_catalog.jsonb_typeof(s.o -> f.fam) = 'array' THEN s.o -> f.fam ELSE '[]'::jsonb END)
     WITH ORDINALITY e(o, i)
   WHERE pg_catalog.jsonb_typeof(e.o) <> 'object' ORDER BY s.i, f.fam, e.i LIMIT 1;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: % must be an object', v_bad USING HINT = 'invalid_payload';
  END IF;
  SELECT pg_catalog.format('sections[%s].metrics[%s].spark[%s]', s.i - 1, m.i - 1, x.i - 1) INTO v_bad
    FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i)
   CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(s.o -> 'metrics') WITH ORDINALITY m(o, i)
   CROSS JOIN LATERAL pg_catalog.jsonb_array_elements(
     CASE WHEN pg_catalog.jsonb_typeof(m.o -> 'spark') = 'array' THEN m.o -> 'spark' ELSE '[]'::jsonb END)
     WITH ORDINALITY x(v, i)
   WHERE pg_catalog.jsonb_typeof(x.v) <> 'number' ORDER BY s.i, m.i, x.i LIMIT 1;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: % must be a number', v_bad USING HINT = 'invalid_payload';
  END IF;

  -- Section identity inside the edition: slug and ord are each unique.
  SELECT pg_catalog.format('slug %s', s.o ->> 'slug') INTO v_bad
    FROM pg_catalog.jsonb_array_elements(v_sections) s(o)
   GROUP BY s.o ->> 'slug' HAVING pg_catalog.count(*) > 1 ORDER BY 1 LIMIT 1;
  IF v_bad IS NULL THEN
    SELECT pg_catalog.format('ord %s', (s.o ->> 'ord')::numeric) INTO v_bad
      FROM pg_catalog.jsonb_array_elements(v_sections) s(o)
     GROUP BY (s.o ->> 'ord')::numeric HAVING pg_catalog.count(*) > 1 ORDER BY 1 LIMIT 1;
  END IF;
  IF v_bad IS NOT NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: duplicate section %', v_bad USING HINT = 'invalid_payload';
  END IF;

  -- The model never owns identity or visibility.
  IF (v_brief ->> 'issue_no')::integer <> p_expected_issue_no
     OR (v_brief ->> 'brief_date') <> pg_catalog.to_char(p_expected_brief_date, 'YYYY-MM-DD') THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload identity (issue %, date %) differs from the trusted identity (issue %, date %)',
      v_brief ->> 'issue_no', v_brief ->> 'brief_date', p_expected_issue_no,
      pg_catalog.to_char(p_expected_brief_date, 'YYYY-MM-DD') USING HINT = 'identity_conflict';
  END IF;
  IF (v_brief ->> 'volume')::integer < 1 THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload volume must be positive' USING HINT = 'invalid_payload';
  END IF;
  IF (v_brief ->> 'status') IS NOT NULL AND (v_brief ->> 'status') <> 'published' THEN
    RAISE EXCEPTION 'publish_brief_atomic: payload status % contradicts a publication request', v_brief ->> 'status'
      USING HINT = 'invalid_payload';
  END IF;

  -- ── Serialise every compliant publisher (held until COMMIT/ROLLBACK) ────
  PERFORM pg_catalog.pg_advisory_xact_lock(c_lock_key);

  -- Everything below runs AFTER the lock, one statement at a time, so each read sees
  -- the state committed by any writer that held the lock before us.
  IF p_expected_brief_date <> (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Dhaka')::date THEN
    RAISE EXCEPTION 'publish_brief_atomic: brief_date % is not the current Bangladesh date %; live publication of another day is refused',
      pg_catalog.to_char(p_expected_brief_date, 'YYYY-MM-DD'),
      pg_catalog.to_char((pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Dhaka')::date, 'YYYY-MM-DD')
      USING HINT = 'wrong_publication_date';
  END IF;

  -- Scoped duplicate guard: only the TARGET date counts (historical duplicate dates never block).
  SELECT pg_catalog.count(*) INTO v_count FROM public.briefs WHERE brief_date = p_expected_brief_date;
  IF v_count > 1 THEN
    RAISE EXCEPTION 'publish_brief_atomic: % rows already exist for %; operator repair required, nothing written',
      v_count, pg_catalog.to_char(p_expected_brief_date, 'YYYY-MM-DD') USING HINT = 'target_date_conflict';
  END IF;

  IF v_count = 1 THEN
    SELECT b.id, b.issue_no, b.status, b.volume INTO STRICT v_target
      FROM public.briefs b WHERE b.brief_date = p_expected_brief_date FOR UPDATE;
    IF v_target.issue_no <> p_expected_issue_no THEN
      RAISE EXCEPTION 'publish_brief_atomic: % already belongs to issue %, not issue %',
        pg_catalog.to_char(p_expected_brief_date, 'YYYY-MM-DD'), v_target.issue_no, p_expected_issue_no
        USING HINT = 'identity_conflict';
    END IF;
    IF v_target.status NOT IN ('published', 'draft') THEN
      RAISE EXCEPTION 'publish_brief_atomic: issue % has unsupported status %', v_target.issue_no, v_target.status
        USING HINT = 'identity_conflict';
    END IF;
    IF v_target.volume <> (v_brief ->> 'volume')::integer THEN
      RAISE EXCEPTION 'publish_brief_atomic: payload volume % differs from stored volume % of issue %',
        v_brief ->> 'volume', v_target.volume, v_target.issue_no USING HINT = 'identity_conflict';
    END IF;
    -- Existing identity (published, or a legacy draft): keep id, issue_no, brief_date,
    -- volume and created_at. Never a notification authorisation.
    v_brief_id := v_target.id;
    v_created := false;
  ELSE
    PERFORM 1 FROM public.briefs b WHERE b.issue_no = p_expected_issue_no FOR UPDATE;
    IF FOUND THEN
      RAISE EXCEPTION 'publish_brief_atomic: issue % already exists on another date', p_expected_issue_no
        USING HINT = 'identity_conflict';
    END IF;
    SELECT COALESCE(pg_catalog.max(b.issue_no), 0) INTO v_max_issue FROM public.briefs b;
    IF p_expected_issue_no <> v_max_issue + 1 THEN
      RAISE EXCEPTION 'publish_brief_atomic: new issue must be % (current maximum + 1), got %',
        v_max_issue + 1, p_expected_issue_no USING HINT = 'identity_conflict';
    END IF;
    INSERT INTO public.briefs (issue_no, volume, brief_date, status)
    VALUES (p_expected_issue_no, (v_brief ->> 'volume')::integer, p_expected_brief_date, 'draft')
    RETURNING id INTO v_brief_id;
    v_created := true;
  END IF;

  -- ── Replace the children of exactly this edition (FK cascades remove the rest) ──
  DELETE FROM public.sections WHERE brief_id = v_brief_id;

  FOR v_section IN
    SELECT s.o FROM pg_catalog.jsonb_array_elements(v_sections) WITH ORDINALITY s(o, i) ORDER BY s.i
  LOOP
    v_section_id := NULL;
    INSERT INTO public.sections (brief_id, slug, ord, title, group_key, freshness, verdict,
                                 verdict_tone, banker_read, weight, tldr, summary_pills,
                                 analysis, chart_read, movers)
    VALUES (v_brief_id,
            v_section.o ->> 'slug',
            (v_section.o ->> 'ord')::integer,
            v_section.o ->> 'title',
            v_section.o ->> 'group_key',
            v_section.o ->> 'freshness',
            v_section.o ->> 'verdict',
            v_section.o ->> 'verdict_tone',
            NULLIF(v_section.o -> 'banker_read', 'null'::jsonb),
            (v_section.o ->> 'weight')::integer,
            v_section.o ->> 'tldr',
            v_section.o -> 'summary_pills',
            v_section.o ->> 'analysis',
            NULLIF(v_section.o -> 'chart_read', 'null'::jsonb),
            NULLIF(v_section.o -> 'movers', 'null'::jsonb))
    RETURNING id INTO v_section_id;
    IF v_section_id IS NULL THEN
      RAISE EXCEPTION 'publish_brief_atomic: section % was not inserted', v_section.o ->> 'slug'
        USING HINT = 'count_mismatch';
    END IF;

    INSERT INTO public.metrics (section_id, ord, label, value, sub, tone, is_snapshot, spark,
                                delta, delta_pct, changed, weight, held_from, next_print)
    SELECT v_section_id, (e.i - 1)::integer, e.o ->> 'label', e.o ->> 'value', e.o ->> 'sub',
           e.o ->> 'tone', (e.o ->> 'is_snapshot')::boolean,
           CASE WHEN pg_catalog.jsonb_typeof(e.o -> 'spark') = 'array'
                THEN ARRAY(SELECT x.v::numeric
                             FROM pg_catalog.jsonb_array_elements_text(e.o -> 'spark') WITH ORDINALITY x(v, n)
                            ORDER BY x.n) END,
           e.o ->> 'delta', e.o ->> 'delta_pct', (e.o ->> 'changed')::boolean,
           (e.o ->> 'weight')::integer, (e.o ->> 'held_from')::date, e.o ->> 'next_print'
      FROM pg_catalog.jsonb_array_elements(v_section.o -> 'metrics') WITH ORDINALITY e(o, i);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> pg_catalog.jsonb_array_length(v_section.o -> 'metrics') THEN
      RAISE EXCEPTION 'publish_brief_atomic: section % inserted % of % metrics', v_section.o ->> 'slug',
        v_rows, pg_catalog.jsonb_array_length(v_section.o -> 'metrics') USING HINT = 'count_mismatch';
    END IF;

    INSERT INTO public.news (section_id, ord, headline, detail, source, source_url, published_at,
                             tone, changed, held_from)
    SELECT v_section_id, (e.i - 1)::integer, e.o ->> 'headline', e.o ->> 'detail', e.o ->> 'source',
           e.o ->> 'source_url', (e.o ->> 'published_at')::timestamptz, e.o ->> 'tone',
           (e.o ->> 'changed')::boolean, (e.o ->> 'held_from')::date
      FROM pg_catalog.jsonb_array_elements(v_section.o -> 'news') WITH ORDINALITY e(o, i);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> pg_catalog.jsonb_array_length(v_section.o -> 'news') THEN
      RAISE EXCEPTION 'publish_brief_atomic: section % inserted % of % news items', v_section.o ->> 'slug',
        v_rows, pg_catalog.jsonb_array_length(v_section.o -> 'news') USING HINT = 'count_mismatch';
    END IF;

    -- series_key = point.key or section.slug (same rule as the Python publisher).
    INSERT INTO public.chart_series (section_id, series_key, ts, value)
    SELECT v_section_id, COALESCE(NULLIF(e.o ->> 'key', ''), v_section.o ->> 'slug'),
           (e.o ->> 'ts')::date, (e.o ->> 'value')::numeric
      FROM pg_catalog.jsonb_array_elements(v_section.o -> 'series') e(o);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> pg_catalog.jsonb_array_length(v_section.o -> 'series') THEN
      RAISE EXCEPTION 'publish_brief_atomic: section % inserted % of % chart points', v_section.o ->> 'slug',
        v_rows, pg_catalog.jsonb_array_length(v_section.o -> 'series') USING HINT = 'count_mismatch';
    END IF;

    INSERT INTO public.chart_notes (section_id, series_key, ts, label, detail)
    SELECT v_section_id, e.o ->> 'series_key', (e.o ->> 'ts')::date, e.o ->> 'label', e.o ->> 'detail'
      FROM pg_catalog.jsonb_array_elements(v_section.o -> 'notes') e(o);
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> pg_catalog.jsonb_array_length(v_section.o -> 'notes') THEN
      RAISE EXCEPTION 'publish_brief_atomic: section % inserted % of % chart notes', v_section.o ->> 'slug',
        v_rows, pg_catalog.jsonb_array_length(v_section.o -> 'notes') USING HINT = 'count_mismatch';
    END IF;
  END LOOP;

  SELECT pg_catalog.count(*) INTO v_rows FROM public.sections WHERE brief_id = v_brief_id;
  IF v_rows <> pg_catalog.jsonb_array_length(v_sections) THEN
    RAISE EXCEPTION 'publish_brief_atomic: edition has % sections, payload has %', v_rows,
      pg_catalog.jsonb_array_length(v_sections) USING HINT = 'count_mismatch';
  END IF;

  -- ── Header content (identity columns and created_at are never touched) ──
  UPDATE public.briefs
     SET read_minutes = (v_brief ->> 'read_minutes')::integer,
         cover_metric = NULLIF(v_brief -> 'cover_metric', 'null'::jsonb),
         todays_call = v_brief ->> 'todays_call',
         lens = v_brief ->> 'lens',
         frame = v_brief ->> 'frame'
   WHERE id = v_brief_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows <> 1 THEN
    RAISE EXCEPTION 'publish_brief_atomic: header update touched % rows', v_rows USING HINT = 'count_mismatch';
  END IF;

  -- A write that crossed Bangladesh midnight must not land on yesterday's date.
  IF p_expected_brief_date <> (pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Dhaka')::date THEN
    RAISE EXCEPTION 'publish_brief_atomic: Bangladesh date changed during the write; nothing published'
      USING HINT = 'wrong_publication_date';
  END IF;

  -- ── The flip: the LAST write (AGENTS.md landmine 22) ─────────────────────
  UPDATE public.briefs
     SET status = 'published', published_at = pg_catalog.clock_timestamp()
   WHERE id = v_brief_id
  RETURNING published_at INTO v_published_at;
  IF v_published_at IS NULL THEN
    RAISE EXCEPTION 'publish_brief_atomic: final publish flip did not apply' USING HINT = 'count_mismatch';
  END IF;

  RETURN pg_catalog.jsonb_build_object(
    'brief_id', v_brief_id,
    'issue_no', p_expected_issue_no,
    'brief_date', pg_catalog.to_char(p_expected_brief_date, 'YYYY-MM-DD'),
    'published_at', v_published_at,
    'created_new_identity', v_created);
END
$fn$;

COMMENT ON FUNCTION public.publish_brief_atomic(integer, date, jsonb) IS
  'R3 atomic publication of one BriefPayloadV6 edition (migration 0006). One transaction: '
  'advisory lock BRIEFPUB, current-Bangladesh-date check, target-date duplicate hold, '
  'max+1 or reuse of the existing daily identity (id, issue_no, brief_date, volume, created_at kept), '
  'child replacement scoped to that brief id, published flip last. Returns '
  '{brief_id, issue_no, brief_date, published_at, created_new_identity}. '
  'Conservative delivery fence: created_new_identity=true is the ONLY notification authorisation; '
  'a committed row means "never send automatically again", not "delivered"; a lost response '
  'leaves a published but possibly unemailed issue for manual provider inspection. '
  'Serialises only callers of this function: legacy/direct service-role table writers must be excluded. '
  'Schema change rule: every payload object must carry EXACTLY the keys in c_spec, so a new column-mapped field '
  '(a new BriefV6/SectionV6/MetricV6/NewsItemV6/SeriesPointV6/SeriesNoteV6 key) needs, in the SAME migration as its '
  'ALTER TABLE ... ADD COLUMN, a CREATE OR REPLACE of this function adding the key to c_spec and to its INSERT/UPDATE '
  'column list; otherwise every publication holds with invalid_payload. A key inside a stored jsonb column '
  '(cover_metric, banker_read, chart_read, summary_pills, movers) needs no change here. '
  'service_role EXECUTE only. After (re)applying: NOTIFY pgrst, ''reload schema''.';

-- ─── 3. Privileges ───────────────────────────────────────────────────────
REVOKE ALL ON FUNCTION public.publish_brief_atomic(integer, date, jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.publish_brief_atomic(integer, date, jsonb) TO service_role;

-- Owner decision (b): the SPA only reads; RLS never covered TRUNCATE.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES, MAINTAIN
  ON TABLE public.briefs, public.sections, public.metrics, public.news,
           public.chart_series, public.chart_notes
  FROM anon, authenticated;

-- ─── 4. Postconditions (any failure rolls the whole migration back) ──────
DO $post$
DECLARE
  v_fn constant regprocedure := 'public.publish_brief_atomic(integer, date, jsonb)'::regprocedure;
  v_rec record;
BEGIN
  IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc
       WHERE pronamespace = 'public'::pg_catalog.regnamespace AND proname = 'publish_brief_atomic') <> 1 THEN
    RAISE EXCEPTION '0006 postcondition: expected exactly one publish_brief_atomic';
  END IF;
  IF (SELECT p.prosecdef OR p.provolatile <> 'v' OR p.proacl IS NULL
             OR NOT ('search_path=""' = ANY (COALESCE(p.proconfig, '{}'::text[])))
        FROM pg_catalog.pg_proc p WHERE p.oid = v_fn) THEN
    RAISE EXCEPTION '0006 postcondition: publish_brief_atomic must be VOLATILE SECURITY INVOKER with search_path="" and an explicit ACL';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_proc p, pg_catalog.aclexplode(p.proacl) a
              WHERE p.oid = v_fn AND a.grantee = 0) THEN
    RAISE EXCEPTION '0006 postcondition: PUBLIC still has EXECUTE on publish_brief_atomic';
  END IF;
  IF pg_catalog.has_function_privilege('anon', v_fn, 'EXECUTE')
     OR pg_catalog.has_function_privilege('authenticated', v_fn, 'EXECUTE')
     OR NOT pg_catalog.has_function_privilege('service_role', v_fn, 'EXECUTE') THEN
    RAISE EXCEPTION '0006 postcondition: EXECUTE on publish_brief_atomic must be service_role only';
  END IF;
  IF NOT pg_catalog.has_function_privilege('anon', 'public.get_latest_brief()', 'EXECUTE')
     OR NOT pg_catalog.has_function_privilege('authenticated', 'public.get_latest_brief()', 'EXECUTE') THEN
    RAISE EXCEPTION '0006 postcondition: get_latest_brief must stay executable by anon and authenticated';
  END IF;
  FOR v_rec IN
    SELECT r.role, t.tbl, p.priv
      FROM (VALUES ('anon'), ('authenticated')) r(role)
     CROSS JOIN (VALUES ('briefs'), ('sections'), ('metrics'), ('news'), ('chart_series'), ('chart_notes')) t(tbl)
     CROSS JOIN (VALUES ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('TRIGGER'), ('REFERENCES'), ('MAINTAIN')) p(priv)
     WHERE pg_catalog.has_table_privilege(r.role, 'public.' || t.tbl, p.priv)
        OR (p.priv IN ('INSERT', 'UPDATE', 'REFERENCES')
            AND pg_catalog.has_any_column_privilege(r.role, 'public.' || t.tbl, p.priv))
  LOOP
    RAISE EXCEPTION '0006 postcondition: % still has % on public.%', v_rec.role, v_rec.priv, v_rec.tbl;
  END LOOP;
  FOR v_rec IN
    SELECT r.role, t.tbl, r.priv
      FROM (VALUES ('anon', 'SELECT'), ('authenticated', 'SELECT'), ('service_role', 'SELECT'),
                   ('service_role', 'INSERT'), ('service_role', 'UPDATE'), ('service_role', 'DELETE')) AS r(role, priv)
     CROSS JOIN (VALUES ('briefs'), ('sections'), ('metrics'), ('news'), ('chart_series'), ('chart_notes')) t(tbl)
     WHERE NOT pg_catalog.has_table_privilege(r.role, 'public.' || t.tbl, r.priv)
  LOOP
    RAISE EXCEPTION '0006 postcondition: % lost % on public.%', v_rec.role, v_rec.priv, v_rec.tbl;
  END LOOP;
END
$post$;

-- PostgREST caches the schema; tell it about the new function (delivered on COMMIT).
NOTIFY pgrst, 'reload schema';

COMMIT;
