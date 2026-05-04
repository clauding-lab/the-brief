export type Tone = "bull" | "bear" | "warn" | "neu";
export type SectionGroup = "overview" | "banking" | "markets" | "realeco" | "policy";
export type DataSource = "static" | "cache" | "live";

export interface CoverMetric {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  section_slug?: string;
  as_of?: string;
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
}

export interface NewsItem {
  headline: string;
  detail?: string;
  source?: string;
  source_url?: string;
  published_at?: string;
  tone?: Tone;
  changed?: boolean;
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
