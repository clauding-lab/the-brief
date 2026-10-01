// THE BRIEF — permalink + archive data access.
//
// There is no `get_brief_by_issue` RPC (only `get_latest_brief` exists —
// docs/handoff/2026-07-04-review-fixes.md flagged this as a blocker
// requiring a new RPC, which needs a Supabase-side migration Adnan applies
// by hand, per AGENTS.md landmine 18). Verified against production instead
// of assuming: `briefs`, `sections`, and their child tables (`metrics`,
// `news`, `chart_series`, `chart_notes`) are anon-readable via plain
// PostgREST embedding. The permalink is ONE request rooted at `briefs`
// (R3c) —
//
//   GET /briefs?issue_no=eq.<n>&status=eq.published
//       &select=<header>,sections(<section>,metrics(..),news(..),chart_series(..),chart_notes(..))
//
// — one SQL statement, so one database snapshot: a same-day correction
// committing mid-read can never pair the old header with the new sections.
// No RPC needed; no schema invented.

import { createClient } from "@supabase/supabase-js";
import type {
  Brief,
  BriefPayload,
  Metric,
  NewsItem,
  Section,
  SeriesNote,
  SeriesPoint,
} from "@/types/brief";

// Explicit columns, not select("*") (review round 1, MED-7): "*" silently
// widens to whatever the table gains next — an explicit list means a new
// column shows up as a deliberate change to this file, not a surprise.
const BRIEF_SELECT =
  "id,issue_no,volume,brief_date,read_minutes,cover_metric,published_at,status,todays_call,lens,frame";

const SECTION_SELECT =
  "slug,ord,title,group_key,freshness,verdict,verdict_tone,banker_read,weight,tldr," +
  "summary_pills,analysis,chart_read,movers," +
  "metrics(label,value,sub,tone,is_snapshot,spark,delta,delta_pct,changed,weight,held_from,next_print,ord)," +
  "news(headline,detail,source,source_url,published_at,tone,changed,held_from,ord)," +
  "chart_series(series_key,ts,value)," +
  "chart_notes(series_key,ts,label,detail)";

// The `metrics`/`news` child tables carry an `ord` column (see
// v6_publisher.py's insert) that isn't part of the SPA's Metric/NewsItem
// shape — it exists purely to sort, then gets dropped.
type RawMetric = Metric & { ord?: number | null };
type RawNews = NewsItem & { ord?: number | null };

interface RawSeriesRow {
  series_key: string | null;
  ts: string;
  value: number;
}

interface RawNoteRow {
  series_key: string;
  ts: string;
  label: string;
  detail?: string | null;
}

interface RawSectionRow {
  slug: string;
  ord: number;
  title: string;
  group_key: Section["group_key"];
  freshness?: Section["freshness"];
  verdict?: string | null;
  verdict_tone?: Section["verdict_tone"];
  banker_read?: Section["banker_read"];
  weight?: Section["weight"];
  tldr?: string | null;
  summary_pills?: Section["summary_pills"];
  analysis?: string | null;
  chart_read?: Section["chart_read"];
  movers?: Section["movers"];
  metrics?: RawMetric[] | null;
  news?: RawNews[] | null;
  chart_series?: RawSeriesRow[] | null;
  chart_notes?: RawNoteRow[] | null;
}

function byOrd(a: { ord?: number | null }, b: { ord?: number | null }): number {
  return (a.ord ?? 0) - (b.ord ?? 0);
}

// Server-side order for the nested children (R3c): sections and ordinal
// children by ord with an id tie-breaker; chart points by time like
// `get_latest_brief`. The adapters below still sort metrics/news by ord.
const NESTED_ORDER: ReadonlyArray<readonly [table: string, column: string]> = [
  ["sections", "ord"],
  ["sections", "id"],
  ["sections.metrics", "ord"],
  ["sections.metrics", "id"],
  ["sections.news", "ord"],
  ["sections.news", "id"],
  ["sections.chart_series", "ts"],
  ["sections.chart_series", "series_key"],
  ["sections.chart_notes", "ts"],
  ["sections.chart_notes", "series_key"],
  ["sections.chart_notes", "id"],
];

function sortedWithoutOrd<T extends { ord?: number | null }>(rows: T[]): Omit<T, "ord">[] {
  return [...rows]
    .sort(byOrd)
    .map((row) => {
      const clone: Record<string, unknown> = { ...row };
      delete clone.ord;
      return clone as Omit<T, "ord">;
    });
}

function toSection(row: RawSectionRow): Section {
  const series: SeriesPoint[] = (row.chart_series ?? []).map((s) => ({
    key: s.series_key ?? undefined,
    ts: s.ts,
    value: s.value,
  }));
  const notes: SeriesNote[] = (row.chart_notes ?? []).map((n) => ({
    series_key: n.series_key,
    ts: n.ts,
    label: n.label,
    detail: n.detail ?? undefined,
  }));
  return {
    slug: row.slug,
    ord: row.ord,
    title: row.title,
    group_key: row.group_key,
    freshness: row.freshness,
    verdict: row.verdict ?? undefined,
    verdict_tone: row.verdict_tone,
    banker_read: row.banker_read ?? null,
    weight: row.weight,
    tldr: row.tldr ?? undefined,
    summary_pills: row.summary_pills ?? undefined,
    analysis: row.analysis ?? undefined,
    chart_read: row.chart_read ?? null,
    movers: row.movers ?? null,
    metrics: sortedWithoutOrd(row.metrics ?? []),
    news: sortedWithoutOrd(row.news ?? []),
    series,
    notes,
  };
}

function readEnv(): { url: string; key: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  return { url, key };
}

function client() {
  const env = readEnv();
  if (!env) return null;
  return createClient(env.url, env.key, {
    auth: { persistSession: false },
    // Bypass Next's fetch Data Cache, matching app/page.tsx's live fetch —
    // an archive/permalink page still reads the current published state.
    global: { fetch: (input, init) => fetch(input, { ...init, cache: "no-store" }) },
  });
}

// RLS posture (review round 1, MED-7 — recorded, not changed here): no
// migration under migrations/ defines a Row Level Security policy for
// `briefs` or `sections`. Draft-hiding for permalinks/archive rests
// ENTIRELY on the two `.eq("status", "published")` filters below being
// present and correct — there is no database-side backstop. Removing
// either filter would serve an in-progress draft (or, per landmine 33, a
// row mid-republish-swap) to an anon reader. The regression test in
// fetchBriefByIssue.test.ts pins that this function always sends that
// filter; it can't verify the database enforces anything, because it
// doesn't.
/** A single published issue by issue_no, or null if it doesn't exist, isn't
 * published, or (landmine 33) is mid-republish-swap with no sections yet. */
export async function fetchBriefByIssueNo(issueNo: number): Promise<BriefPayload | null> {
  const sb = client();
  if (!sb) return null;

  let query = sb
    .from("briefs")
    .select(`${BRIEF_SELECT},sections(${SECTION_SELECT})`)
    .eq("issue_no", issueNo)
    .eq("status", "published");
  for (const [referencedTable, column] of NESTED_ORDER) {
    query = query.order(column, { referencedTable, ascending: true });
  }
  const { data: briefs, error: briefErr } = await query.limit(1);
  if (briefErr || !briefs?.length) return null;
  const { sections: sectionRows, ...brief } = briefs[0] as unknown as Brief & {
    id: string;
    sections?: RawSectionRow[] | null;
  };

  // Never render an edition with no content: a published header whose
  // sections are missing or empty is "not found". Since migration 0006 a
  // publication commits header and sections together, so this is a guard
  // for legacy/partial rows (AGENTS.md landmine 33), not a race window.
  if (!sectionRows || sectionRows.length === 0) return null;

  const sections = sectionRows.map(toSection);
  return { brief, sections };
}

export interface ArchiveEntry {
  issue_no: number;
  brief_date: string;
  todays_call: string | null;
}

/** Every published issue, newest first — for the /archive index. */
export async function fetchArchiveIndex(limit = 500): Promise<ArchiveEntry[]> {
  const sb = client();
  if (!sb) return [];
  const { data, error } = await sb
    .from("briefs")
    .select("issue_no,brief_date,todays_call")
    .eq("status", "published")
    .order("issue_no", { ascending: false })
    .limit(limit);
  if (error) return [];
  return (data ?? []) as ArchiveEntry[];
}

// Exported for tests only (review round 2, optional) — lets
// fetchBriefByIssue.test.ts assert the briefs query sends exactly this
// column list, not just "some string that isn't *".
export const __internals = { BRIEF_SELECT, SECTION_SELECT };
