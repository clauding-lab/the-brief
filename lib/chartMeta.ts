// THE BRIEF — chart caption / staleness / a11y-label helpers.
//
// Section.tsx's "LATEST:" strip used to read `metrics[0]` — the section's
// FIRST stored metric tile, which has no relationship to whichever series
// is actually plotted (bug: the bb/"FX Reserves" chart captioned "Overnight
// Call Money 9.31%" because that happened to be metrics[0] for that section).
// Everything here derives caption/staleness/aria-label content from the
// section's own `series` payload — the same data Chart.js plots — so the
// caption can never drift from the chart again.
//
// One spec per chartConfigs.ts ChartConfigKey. `primaryKey` names the single
// series shown in the "Latest:" strip; `allKeys` lists every series the
// chart plots, used for staleness (the OLDEST-ending series among them wins,
// so e.g. an imports band that dies while exports keeps updating still
// flags the chart as stale — see fxBalanceConfig's 3-series diverging area).

import type { Section, SeriesPoint } from "@/types/brief";
import type { ChartConfigKey } from "./chartConfigs";

interface ChartSpec {
  primaryKey: string;
  primaryLabel: string;
  format: (v: number) => string;
  allKeys: string[];
  cadence: "daily" | "monthly";
  /** Days since the section's issue date before the chart is flagged stale. */
  thresholdDays: number;
}

// Round-to-2-decimals string formatter, kept local — chartConfigs.ts's `r2str`
// is an internal helper (see its `__internals` export comment: "not part of
// the public API surface for Section.tsx"), so this file doesn't reach into it.
function num2(v: number): string {
  const r = Math.round(v * 100) / 100;
  return String(r);
}

const DAILY_THRESHOLD_DAYS = 10; // a few missed trading/weekend days + one holiday
const MONTHLY_THRESHOLD_DAYS = 55; // ~1 month + typical reporting lag

const CHART_SPECS: Partial<Record<ChartConfigKey, ChartSpec>> = {
  reserves: {
    primaryKey: "gross_reserves_usd_bn_monthly",
    primaryLabel: "Gross reserves",
    format: (v) => `$${num2(v)}bn`,
    allKeys: ["gross_reserves_usd_bn_monthly", "net_reserves_bpm6_usd_bn_monthly"],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
  fxBalance: {
    primaryKey: "exports_usd_mn_monthly",
    primaryLabel: "Exports",
    format: (v) => `$${num2(v / 1000)}bn`,
    allKeys: ["exports_usd_mn_monthly", "imports_usd_mn_monthly", "remittance_usd_mn_monthly"],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
  dsex: {
    primaryKey: "dsex",
    primaryLabel: "DSEX",
    format: (v) => v.toLocaleString(undefined, { maximumFractionDigits: 2 }),
    allKeys: ["dsex"],
    cadence: "daily",
    thresholdDays: DAILY_THRESHOLD_DAYS,
  },
  brent: {
    primaryKey: "brent",
    primaryLabel: "Brent",
    format: (v) => `$${num2(v)}`,
    allKeys: ["brent"],
    cadence: "daily",
    thresholdDays: DAILY_THRESHOLD_DAYS,
  },
  yieldLadder: {
    primaryKey: "yield_10y_monthly",
    primaryLabel: "10Y yield",
    format: (v) => `${v.toFixed(2)}%`,
    allKeys: [
      "tbill_91d_yield_monthly",
      "tbill_182d_yield_monthly",
      "tbill_364d_yield_monthly",
      "yield_2y_monthly",
      "yield_5y_monthly",
      "yield_10y_monthly",
      "yield_15y_monthly",
      "yield_20y_monthly",
    ],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
  cpiTrend: {
    primaryKey: "cpi_12m_avg_monthly",
    primaryLabel: "Headline CPI (12m avg)",
    format: (v) => `${num2(v)}%`,
    allKeys: ["cpi_12m_avg_monthly", "cpi_p2p_food_monthly", "cpi_p2p_nonfood_monthly"],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
  remitFlow: {
    primaryKey: "remittance_usd_mn_monthly",
    primaryLabel: "Remittance",
    format: (v) => `$${Math.round(v).toLocaleString()}mn`,
    allKeys: ["remittance_usd_mn_monthly"],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
  fiscalNbr: {
    primaryKey: "nbr_revenue_monthly_cr",
    primaryLabel: "NBR revenue",
    format: (v) => `Tk ${Math.round(v).toLocaleString()} cr`,
    allKeys: ["nbr_revenue_monthly_cr"],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
  lng: {
    primaryKey: "lng_jkm",
    primaryLabel: "LNG JKM",
    format: (v) => `$${num2(v)}/MMBtu`,
    allKeys: ["lng_jkm"],
    cadence: "monthly",
    thresholdDays: MONTHLY_THRESHOLD_DAYS,
  },
};

function formatMonthYear(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const idx = parseInt(m[2], 10) - 1;
  return idx >= 0 && idx <= 11 ? `${months[idx]} ${m[1]}` : iso;
}

export interface ChartLatest {
  label: string;
  value: string;
  ts: string;
}

/**
 * "Latest: {label} {value}" strip content, sourced from the section's own
 * plotted series — never from `metrics[0]`. Falls back to the single most
 * recent point across ALL of the section's series when no spec is defined
 * for `configKey` (e.g. a future chart added to SECTION_TO_CHART before a
 * spec is written here, or the SignatureChart fallback path).
 */
export function getChartLatestCaption(
  section: Section,
  configKey: ChartConfigKey | null,
): ChartLatest | null {
  const spec = configKey ? CHART_SPECS[configKey] : undefined;
  if (spec) {
    let best: SeriesPoint | null = null;
    for (const p of section.series) {
      if (p.key !== spec.primaryKey) continue;
      if (!best || p.ts > best.ts) best = p;
    }
    if (best) return { label: spec.primaryLabel, value: spec.format(best.value), ts: best.ts };
  }
  let best: SeriesPoint | null = null;
  for (const p of section.series) {
    if (!best || p.ts > best.ts) best = p;
  }
  if (!best) return null;
  const label = (best.key || "Series").replace(/_/g, " ");
  return { label, value: String(best.value), ts: best.ts };
}

export interface ChartStaleness {
  isStale: boolean;
  /** ISO date of the oldest-ending series among the chart's datasets. */
  lastTs: string;
  /** "Series ends {Mon YYYY}" — ready to render, no blur, text stays crisp. */
  label: string;
}

/**
 * Flags a chart stale when the WORST (earliest-ending) of its plotted series
 * is older than a cadence-appropriate threshold vs. the issue date. Using the
 * worst series (not the freshest) catches a chart where one line dies while
 * a sibling keeps updating — e.g. an imports band frozen while exports and
 * remittance continue.
 */
export function getChartStaleness(
  section: Section,
  configKey: ChartConfigKey,
  issueDateIso?: string,
): ChartStaleness | null {
  const spec = CHART_SPECS[configKey];
  if (!spec) return null;
  const latestByKey = new Map<string, string>();
  for (const p of section.series) {
    const k = p.key ?? "";
    if (!spec.allKeys.includes(k)) continue;
    const cur = latestByKey.get(k);
    if (!cur || p.ts > cur) latestByKey.set(k, p.ts);
  }
  if (latestByKey.size === 0) return null;
  const worst = [...latestByKey.values()].sort()[0];
  const worstDate = new Date(`${worst}T00:00:00Z`);
  if (isNaN(worstDate.getTime())) return null;
  const reference = issueDateIso ? new Date(issueDateIso) : new Date();
  const refTime = isNaN(reference.getTime()) ? Date.now() : reference.getTime();
  const days = Math.floor((refTime - worstDate.getTime()) / 86400000);
  return {
    isStale: days > spec.thresholdDays,
    lastTs: worst,
    label: `Series ends ${formatMonthYear(worst)}`,
  };
}

/** Full plotted date span across every series the section carries. */
function getChartDateRange(section: Section): { start: string; end: string } | null {
  if (!section.series.length) return null;
  let min = section.series[0].ts;
  let max = section.series[0].ts;
  for (const p of section.series) {
    if (p.ts < min) min = p.ts;
    if (p.ts > max) max = p.ts;
  }
  return { start: min, end: max };
}

/**
 * Builds a meaningful aria-label for a chart wrapper, e.g.
 * "FX Reserves, monthly, Jun 2025–Jul 2026, latest Gross reserves $36.4bn" —
 * replaces the previous static "{section title} chart" label.
 */
export function getChartAriaLabel(
  section: Section,
  configKey: ChartConfigKey | null,
  head?: { title: string; subtitle?: string },
): string {
  const spec = configKey ? CHART_SPECS[configKey] : undefined;
  const range = getChartDateRange(section);
  const latest = getChartLatestCaption(section, configKey);
  const parts: string[] = [head?.title || `${section.title} chart`];
  if (spec) parts.push(spec.cadence);
  if (range) parts.push(`${formatMonthYear(range.start)}–${formatMonthYear(range.end)}`);
  if (latest) parts.push(`latest ${latest.label} ${latest.value}`);
  return parts.join(", ");
}
