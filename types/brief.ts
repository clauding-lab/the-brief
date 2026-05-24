export type Tone = "bull" | "bear" | "warn" | "neu";
export type SectionGroup = "overview" | "banking" | "markets" | "realeco" | "policy";
export type FreshnessKind = "fresh" | "warning" | "stale" | "unavailable" | "warming_up";
export type DataSource = "static" | "cache" | "live";

export interface CoverMetric {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  section_slug?: string;
  as_of?: string;
  held_from?: string;
  next_print?: string;
}

export interface Brief {
  id?: string;
  issue_no: number;
  volume: number;
  brief_date: string;
  read_minutes?: number;
  cover_metric?: CoverMetric;
  published_at?: string;
  status?: string;
  todays_call?: string;
  lens?: string;
  frame?: string;
}

export interface Metric {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  is_snapshot?: boolean;
  spark?: number[];
  delta?: string;
  delta_pct?: string;
  changed?: boolean;
  weight?: number;
  held_from?: string;
  next_print?: string;
}

export interface NewsItem {
  headline: string;
  detail?: string;
  source?: string;
  source_url?: string;
  published_at?: string;
  tone?: Tone;
  changed?: boolean;
  held_from?: string;
}

export interface SeriesPoint {
  key?: string;
  ts: string;
  value: number;
}

export interface SeriesNote {
  series_key: string;
  ts: string;
  label: string;
  detail?: string;
}

export interface SummaryPill {
  key: string;
  value: string;
  tone?: Tone;
}

export interface BankerRead {
  verdict: string;
  watch?: string[];
  risk?: string[];
  runway?: { value: string; unit: string };
}

export interface Section {
  id?: string;
  slug: string;
  ord: number;
  title: string;
  group_key: SectionGroup;
  freshness?: FreshnessKind;
  verdict?: string;
  verdict_tone?: Tone;
  banker_read?: BankerRead | null;
  weight?: 1 | 2;
  tldr?: string;
  summary_pills?: SummaryPill[];
  analysis?: string;
  metrics: Metric[];
  news: NewsItem[];
  series: SeriesPoint[];
  notes: SeriesNote[];
}

export interface BriefPayload {
  brief: Brief;
  sections: Section[];
  _source?: DataSource;
  _fetchedAt?: number;
  _cachedAt?: number;
}

// --- Long View (pinned editorial insert, v1.2.0+) ---
// v1.2.0 replaces the single-shape model with a composable Block system.
// v1.3.0 adds `bar-chart` for ranked-value visualisations with an optional
// vertical reference line (the first chart-bearing upload landed 2026-05-24).

export interface ProseBlock {
  kind: "prose";
  paragraphs: string[];          // 1-3 paragraphs; never more
}

export interface ComparisonRow {
  title: string;                 // "Penal interest on overdue loans"
  before: string;                // "1.5%" | "BANNED" | "Revealed"
  after: string;                 // "0.5%" | "AT 7.5%" | "Rescheduled"
  description: string;           // 1-line context (required)
  tone?: Tone;                   // optional; "bull"|"bear"|"neu" semantically meaningful
}

export interface ComparisonBlock {
  kind: "comparison";
  before_label: string;          // "Interim" — short, 1-2 words ideal
  after_label: string;           // "BNP-led" — short, 1-2 words ideal
  rows: ComparisonRow[];         // 3-10 rows typical; auto 3-col grid when >= 7
}

export interface StatBlock {
  kind: "stat";
  value: string;                 // "3.8" | "12,400" | "10.0"
  unit?: string;                 // "×" | "CR" | "%" | "BPS" — rendered smaller
  label: string;                 // small-caps eyebrow text
  body: string;                  // 1-2 sentence framing paragraph
  tone?: Tone;                   // optional; tints just the value
}

export interface BulletListItem {
  text: string;                  // supports inline **bold** via markdown-light
  tone?: Tone;                   // optional; tints just the leading mark
}

export interface BulletListBlock {
  kind: "bullet-list";
  eyebrow?: string;              // optional small-caps header above the list
  items: BulletListItem[];       // 2-7 items
}

export interface BarChartItem {
  label: string;                 // e.g., "BRAC Bank"
  value: number;                 // numeric, used for bar-length scaling
  display?: string;              // optional override; defaults to value.toLocaleString()
  tone?: Tone;                   // optional bar tint
}

export interface BarChartReference {
  value: number;                 // position of the vertical reference line
  label: string;                 // text drawn next to the line, e.g., "BDT 2,000 cr"
}

export interface BarChartBlock {
  kind: "bar-chart";
  eyebrow?: string;              // optional small-caps header
  unit?: string;                 // e.g., "Tk cr" — rendered as a caption
  reference?: BarChartReference; // optional vertical dashed line
  items: BarChartItem[];         // 2-12 items, in display order (top to bottom)
}

export type Block =
  | ProseBlock
  | ComparisonBlock
  | StatBlock
  | BulletListBlock
  | BarChartBlock;

export interface LongViewData {
  posted_at: string;             // ISO 8601 UTC (unchanged from v1.1.0)
  title: string;                 // 5–10 words (unchanged)
  lead: string;                  // 1–2 sentences (unchanged)
  blocks: Block[];               // REPLACES v1.1.0's body_paragraphs + chart_spec
  banker_read: string;           // 1 paragraph (unchanged)
}
