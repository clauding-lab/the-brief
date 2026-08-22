// THE BRIEF — permalink + archive data access.
//
// There is no `get_brief_by_issue` RPC (only `get_latest_brief` exists —
// docs/handoff/2026-07-04-review-fixes.md flagged this as a blocker
// requiring a new RPC, which needs a Supabase-side migration Adnan applies
// by hand, per AGENTS.md landmine 18). Verified against production instead
// of assuming: `briefs`, `sections`, and their child tables (`metrics`,
// `news`, `chart_series`, `chart_notes`) are anon-readable via plain
// PostgREST embedding —
//
//   GET /sections?brief_id=eq.<id>&select=*,metrics(*),news(*),chart_series(*),chart_notes(*)
//
// — the exact query shape `brief/v6_publisher.py::fetch_previous_brief`
// already uses server-side. No RPC needed; no schema invented.

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

/** A single published issue by issue_no, or null if it doesn't exist / isn't published. */
export async function fetchBriefByIssueNo(issueNo: number): Promise<BriefPayload | null> {
  const sb = client();
  if (!sb) return null;

  const { data: briefs, error: briefErr } = await sb
    .from("briefs")
    .select("*")
    .eq("issue_no", issueNo)
    .eq("status", "published")
    .limit(1);
  if (briefErr || !briefs?.length) return null;
  const brief = briefs[0] as Brief & { id: string };

  const { data: sectionRows, error: sectionErr } = await sb
    .from("sections")
    .select(SECTION_SELECT)
    .eq("brief_id", brief.id)
    .order("ord", { ascending: true });
  if (sectionErr) return null;

  const sections = ((sectionRows ?? []) as unknown as RawSectionRow[]).map(toSection);
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
