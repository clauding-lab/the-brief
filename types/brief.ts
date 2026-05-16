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

// --- Long View (pinned editorial insert, v1.1.0+) ---

export interface ChartSpecSeries {
  name: string;
  data: Array<[string | number, number]>; // [x, y] tuples; x can be a label or ISO date
}

export interface ChartSpecAnnotation {
  x: string | number;
  label: string;
}

export interface ChartSpec {
  kind: "line" | "bar" | "stacked_bar" | "donut";
  title: string;
  x_axis: string;
  y_axis: string;
  series: ChartSpecSeries[];
  annotations?: ChartSpecAnnotation[];
}

export interface LongViewData {
  posted_at: string;          // ISO 8601 UTC; rendered to Asia/Dhaka in the eyebrow
  title: string;              // 5–10 words, no trailing punctuation
  lead: string;               // 1–2 sentences
  body_paragraphs: string[];  // 1–3 paragraphs
  chart_spec: ChartSpec | null; // v1.1.0: always null. v1.1.1: chart-capable.
  banker_read: string;        // 1 paragraph takeaway
}
