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
// Review round 1 (C1): even bound to the right series, the plotted point can
// be a different VINTAGE than the neighboring tile (tbond 10.24 vs a tile's
// 9.23; fx $4.2bn vs $4.03bn) — both numbers can be honest and still
// disagree, because a chart plots a monthly/period series while a tile can
// read a daily or YTD one. The caption now ALWAYS names the plotted period
// ("LATEST PLOTTED · {label} {value} · {Mon YYYY}") so a reader never mistakes
// "what the chart last plotted" for "today's number."
//
// Philosophy note (MED-3): `brief/cadence.py` owns SECTION- and METRIC-level
// freshness badges (fresh/warning/stale, cadence-aware, with a writer-
// liveness twist for `event` metrics — see AGENTS.md landmine 24). This file
// is a separate, simpler, PER-SERIES presentational signal for whether the
// exact line/band a chart plots has usable recent data. Same directional
// philosophy (age vs. a cadence threshold) and now the same period-end
// normalization idea, but deliberately not the same code path and not a
// reproduction of the server's 3-tier fresh/warning/stale system — just a
// binary "is this plotted series worth trusting visually" flag per dataset.
//
// One spec per chartConfigs.ts ChartConfigKey. `primaryKey` names the single
// series shown in the "LATEST PLOTTED" strip; `series` lists every dataset
// the chart plots with a short label each, used for PER-SERIES staleness
// (H6): a multi-series chart where imports dies while exports keeps updating
// should name and dim the imports line specifically, not blanket-dim the
// whole canvas or blanket-mute the whole chart under whichever series is
// worst.

import type { Section, SeriesPoint } from "@/types/brief";
import type { ChartConfigKey } from "./chartConfigs";

export type ChartCadence = "daily" | "monthly";

export interface SeriesInfo {
  key: string;
  /** Short, all-context label for staleness notes, e.g. "Imports" → "IMPORTS ENDS MAR 2026". */
  label: string;
}

interface ChartSpec {
  primaryKey: string;
  primaryLabel: string;
  format: (v: number) => string;
  series: SeriesInfo[];
  cadence: ChartCadence;
}

// Round-to-2-decimals string formatter that NEVER drops a trailing zero
// (Math.round(v*100)/100 followed by String() silently returned "36.4" for
// 36.40, one digit short of the tile precision it's meant to match).
// Kept local — chartConfigs.ts's `r2str` is an internal helper (see its
// `__internals` export comment: "not part of the public API surface for
// Section.tsx"), so this file doesn't reach into it.
function num2(v: number): string {
  return v.toFixed(2);
}

// Locale pinned to "en-GB" everywhere a number/date is formatted for
// display (AGENTS.md landmine 10's spirit extended to number formatting):
// `toLocaleString(undefined, …)` inherits the BROWSER's locale, so a reader
// with bn-BD in their OS/browser settings would see Bengali digits — and
// since the server always renders with its own (non-bn-BD) default, that's
// also a guaranteed hydration mismatch, not just a cosmetic difference.
const LOCALE = "en-GB";

// Server-aligned (MED-3): brief/cadence.py's own `monthly` warning ceiling is
// 45 days past `as_of`; `daily` allows a 2-trading-day gap, which a flat
// calendar-day proxy rounds up to a week to absorb weekends/holidays without
// hand-rolling BD-trading-day math here.
const DAILY_THRESHOLD_DAYS = 7;
const MONTHLY_THRESHOLD_DAYS = 45;
const THRESHOLD_DAYS: Record<ChartCadence, number> = {
  daily: DAILY_THRESHOLD_DAYS,
  monthly: MONTHLY_THRESHOLD_DAYS,
};

const CHART_SPECS: Partial<Record<ChartConfigKey, ChartSpec>> = {
  reserves: {
    primaryKey: "gross_reserves_usd_bn_monthly",
    primaryLabel: "Gross reserves",
    format: (v) => `$${num2(v)}bn`,
    series: [
      { key: "gross_reserves_usd_bn_monthly", label: "Gross reserves" },
      { key: "net_reserves_bpm6_usd_bn_monthly", label: "Net reserves (BPM6)" },
    ],
    cadence: "monthly",
  },
  fxBalance: {
    primaryKey: "exports_usd_mn_monthly",
    primaryLabel: "Exports",
    format: (v) => `$${num2(v / 1000)}bn`,
    series: [
      { key: "exports_usd_mn_monthly", label: "Exports" },
      { key: "imports_usd_mn_monthly", label: "Imports" },
      { key: "remittance_usd_mn_monthly", label: "Remittance" },
    ],
    cadence: "monthly",
  },
  dsex: {
    primaryKey: "dsex",
    primaryLabel: "DSEX",
    format: (v) => v.toLocaleString(LOCALE, { maximumFractionDigits: 2 }),
    series: [{ key: "dsex", label: "DSEX" }],
    cadence: "daily",
  },
  brent: {
    primaryKey: "brent",
    primaryLabel: "Brent",
    format: (v) => `$${num2(v)}`,
    series: [{ key: "brent", label: "Brent" }],
    cadence: "daily",
  },
  yieldLadder: {
    primaryKey: "yield_10y_monthly",
    primaryLabel: "10Y yield",
    format: (v) => `${v.toFixed(2)}%`,
    series: [
      { key: "tbill_91d_yield_monthly", label: "91D" },
      { key: "tbill_182d_yield_monthly", label: "182D" },
      { key: "tbill_364d_yield_monthly", label: "364D" },
      { key: "yield_2y_monthly", label: "2Y" },
      { key: "yield_5y_monthly", label: "5Y" },
      { key: "yield_10y_monthly", label: "10Y" },
      { key: "yield_15y_monthly", label: "15Y" },
      { key: "yield_20y_monthly", label: "20Y" },
    ],
    cadence: "monthly",
  },
  cpiTrend: {
    primaryKey: "cpi_12m_avg_monthly",
    primaryLabel: "Headline CPI (12m avg)",
    format: (v) => `${num2(v)}%`,
    series: [
      { key: "cpi_12m_avg_monthly", label: "Headline CPI" },
      { key: "cpi_p2p_food_monthly", label: "Food CPI" },
      { key: "cpi_p2p_nonfood_monthly", label: "Non-food CPI" },
    ],
    cadence: "monthly",
  },
  remitFlow: {
    primaryKey: "remittance_usd_mn_monthly",
    primaryLabel: "Remittance",
    format: (v) => `$${Math.round(v).toLocaleString(LOCALE)}mn`,
    series: [{ key: "remittance_usd_mn_monthly", label: "Remittance" }],
    cadence: "monthly",
  },
  fiscalNbr: {
    primaryKey: "nbr_revenue_monthly_cr",
    primaryLabel: "NBR revenue",
    format: (v) => `Tk ${Math.round(v).toLocaleString(LOCALE)} cr`,
    series: [{ key: "nbr_revenue_monthly_cr", label: "NBR revenue" }],
    cadence: "monthly",
  },
  // No `lng` entry: the commodities section (§comm) that plotted LNG JKM was
  // retired (AGENTS.md landmine 30) — chartConfigs.ts's `lngConfig` builder
  // and its `SECTION_TO_CHART`/`CHART_CARD_HEADS` rows are unreachable dead
  // code there too, but that cleanup belongs to chartConfigs.ts, not here.
};

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Normalizes an ISO date to the date its cadence's PERIOD actually ends on.
 * Monthly rows in production are stamped inconsistently — some at the
 * month's 1st, some at its last day (verified live: `gross_reserves_usd_bn_
 * monthly` has both conventions across its own history) — and a 1st-of-month
 * stamp reads as ~30 days older than a last-day stamp for the exact same
 * reporting period. Normalizing both to the period's last day before
 * computing age means a threshold sweep can't accidentally fire on the
 * stamping convention instead of real staleness. Daily series need no
 * normalization — the ts already names a single day. */
function periodEnd(iso: string, cadence: ChartCadence): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return iso;
  if (cadence === "daily") return iso;
  const year = parseInt(m[1], 10);
  const month = parseInt(m[2], 10);
  // Day 0 of the NEXT month = the last day of THIS month (handles Feb/leap
  // years correctly via the Date constructor's own month-rollover, in UTC so
  // this never depends on the machine's local timezone).
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${m[1]}-${m[2]}-${pad2(lastDay)}`;
}

function daysBetween(isoDate: string, ref: Date): number {
  const d = new Date(`${isoDate}T00:00:00Z`);
  if (isNaN(d.getTime())) return 0;
  return Math.floor((ref.getTime() - d.getTime()) / 86400000);
}

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
  /** "Jul 2026" — the plotted point's own period, always shown next to the
   * value so a reader can never mistake it for "today's number" when a
   * neighboring tile reads a different (also honest) vintage. */
  periodLabel: string;
}

/**
 * "LATEST PLOTTED · {label} {value} · {Mon YYYY}" content, sourced from the
 * section's own plotted series — never from `metrics[0]`, and always naming
 * its period so it can't be read as agreeing (or disagreeing) with a tile
 * of a different vintage. Falls back to the single most recent point across
 * ALL of the section's series when no spec is defined for `configKey` (e.g.
 * a future chart added to SECTION_TO_CHART before a spec is written here, or
 * the SignatureChart fallback path).
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
    if (best) {
      return {
        label: spec.primaryLabel,
        value: spec.format(best.value),
        ts: best.ts,
        periodLabel: formatMonthYear(best.ts),
      };
    }
  }
  let best: SeriesPoint | null = null;
  for (const p of section.series) {
    if (!best || p.ts > best.ts) best = p;
  }
  if (!best) return null;
  const label = (best.key || "Series").replace(/_/g, " ");
  return { label, value: String(best.value), ts: best.ts, periodLabel: formatMonthYear(best.ts) };
}

export interface PerSeriesStaleness {
  key: string;
  label: string;
  /** ISO date of this specific series' latest point. */
  lastTs: string;
  isStale: boolean;
  /** "IMPORTS ENDS MAR 2026" — ready to render, no blur, text stays crisp. */
  noteLabel: string;
}

/**
 * Per-series staleness (H6): returns EVERY dataset the chart plots with its
 * own isStale flag, instead of collapsing a multi-series chart to a single
 * worst-of verdict. Worst-of is right for DETECTING that a chart needs a
 * closer look; it's wrong for LABELING, because it can't say which line
 * actually died — verified live: fx's imports line stops in Mar 2026 while
 * its exports/remittance lines are current, and a single "the fx chart is
 * stale" flag can't distinguish that from all three dying together.
 *
 * Ages are computed against the CADENCE-NORMALIZED period end (see
 * `periodEnd`), not the raw stamp, so a 1st-of-month row isn't punished for
 * a stamping convention it didn't choose.
 */
export function getPerSeriesStaleness(
  section: Section,
  configKey: ChartConfigKey,
  issueDateIso?: string,
): PerSeriesStaleness[] {
  const spec = CHART_SPECS[configKey];
  if (!spec) return [];

  const latestByKey = new Map<string, string>();
  for (const p of section.series) {
    const k = p.key ?? "";
    const cur = latestByKey.get(k);
    if (!cur || p.ts > cur) latestByKey.set(k, p.ts);
  }

  const reference = issueDateIso ? new Date(issueDateIso) : new Date();
  const refTime = isNaN(reference.getTime()) ? new Date() : reference;
  const threshold = THRESHOLD_DAYS[spec.cadence];

  const out: PerSeriesStaleness[] = [];
  for (const info of spec.series) {
    const lastTs = latestByKey.get(info.key);
    if (!lastTs) continue;
    const normalized = periodEnd(lastTs, spec.cadence);
    const age = daysBetween(normalized, refTime);
    const isStale = age > threshold;
    out.push({
      key: info.key,
      label: info.label,
      lastTs,
      isStale,
      noteLabel: `${info.label.toUpperCase()} ENDS ${formatMonthYear(lastTs).toUpperCase()}`,
    });
  }
  return out;
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
 * "FX Reserves, monthly, Jun 2025–Jul 2026, latest Gross reserves $36.42bn
 * (Jul 2026)" — replaces the previous static "{section title} chart".
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
  if (latest) parts.push(`latest ${latest.label} ${latest.value} (${latest.periodLabel})`);
  return parts.join(", ");
}

// Exported for tests only — not part of the public API surface for
// Section.tsx/BriefChart.tsx.
export const __internals = { periodEnd, daysBetween, formatMonthYear, num2, CHART_SPECS };
