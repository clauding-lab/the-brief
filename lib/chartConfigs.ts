// THE BRIEF — Chart.js config builders.
//
// Pure functions that take a BuildContext (series + optional notes) and
// return Chart.js 4.x configs. Adapted from EconDelta's chartConfigs.js
// (pwa/pages/macro/chartConfigs.js) into TypeScript with the brief's
// typographic-newspaper theme: thinner strokes, fewer area fills, mono
// type, palette read from CSS vars at chart-build time.
//
// All builders MUST handle empty/missing series gracefully — return a
// config with empty datasets so Chart.js renders blank without crashing.
//
// Backend contract: the brief's SectionV6 model surfaces series notes
// (event annotations) on each section as `notes: SeriesNoteV6[]`. The
// DSEX builder consumes these to render event markers.

import type {
  Chart as ChartType,
  ChartArea,
  ChartConfiguration,
  ChartDataset,
  ChartEvent,
  ChartType as ChartJSType,
  Plugin,
  Scale,
} from "chart.js";

import type { SeriesNote } from "@/types/brief";

// ----------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------

/** Inner shape charts consume: series keyed by metric, each a list of [ts, value]. */
export type SeriesByKey = Record<string, Array<[string, number | null]>>;

export interface BuildContext {
  series: SeriesByKey;
  notes?: SeriesNote[];
  /** Series keys flagged stale by chartMeta.ts's per-series check (H6) — a
   * multi-series builder dims ONLY the datasets whose key is in this set,
   * instead of the whole canvas going dim. Absent/empty means "nothing to
   * dim" (draw at full strength). */
  staleKeys?: ReadonlySet<string>;
  /** True when the viewer has prefers-reduced-motion: reduce — builders that
   * set their own `animation` block (bypassing baseLineOptions) must also
   * check this directly. */
  reducedMotion?: boolean;
}

interface XYPoint {
  x: string | number;
  y: number | null;
}

interface BaseLineOptionsArgs {
  legend?: boolean;
  reducedMotion?: boolean;
  yTicks?: {
    callback?: (v: number) => string;
    [k: string]: unknown;
  };
}

// Low-alpha tint of a solid ink, reusing the same hue — the shared "dim this
// dataset" treatment for a stale series (mirrors fxBalanceConfig's existing
// area-fill tint, generalized so any multi-series builder can mute one line
// without touching its siblings).
const STALE_ALPHA = 35; // vs. AREA_ALPHA's 18 for fills — a stale LINE needs to read as muted, not just tinted
function dimColor(ink: string): string {
  return `color-mix(in oklch, ${ink} ${STALE_ALPHA}%, transparent)`;
}

interface EventMarker {
  date: string;
  color: string;
  title: string;
}

// Internal extension used by the event-marker plugin to track hover state.
type ChartWithHoverIdx = ChartType & { $hoveredMarkerIdx?: number | null };

// ----------------------------------------------------------------------
// Theme — read CSS vars at chart-build time so charts respect the brief
// palette (and any future light/dark switch).
// ----------------------------------------------------------------------

function cssVar(name: string, fallback: string): string {
  if (typeof document === "undefined" || !document.documentElement) return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

interface Palette {
  ink: string;
  ink2: string;
  ink3: string;
  ink4: string;
  rule: string;
  ruleSoft: string;
  ruleFaint: string;
  paper: string;
  accent: string;
  accentSoft: string;
  bull: string;
  bear: string;
  warn: string;
}

function buildPalette(): Palette {
  return {
    ink: cssVar("--ink", "#2B0E12"),
    ink2: cssVar("--ink-2", "#4A1F24"),
    ink3: cssVar("--ink-3", "#7A5C5F"),
    ink4: cssVar("--ink-4", "#A5908F"),
    rule: cssVar("--rule", "#2B0E12"),
    ruleSoft: cssVar("--rule-soft", "rgba(43, 14, 18, 0.18)"),
    ruleFaint: cssVar("--rule-faint", "rgba(43, 14, 18, 0.08)"),
    paper: cssVar("--paper", "#EDE7DD"),
    accent: cssVar("--accent", "oklch(0.42 0.14 25)"),
    accentSoft: cssVar("--accent-soft", "oklch(0.42 0.14 25 / 0.12)"),
    bull: cssVar("--bull", "oklch(0.42 0.10 150)"),
    bear: cssVar("--bear", "oklch(0.45 0.16 25)"),
    warn: cssVar("--warn", "oklch(0.55 0.13 70)"),
  };
}

// Mono typeface — the brief's body type is JetBrains Mono via --mono.
const FONT = {
  family:
    "var(--mono), 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
};

// ----------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------

function toPoints(
  series: Array<[string, number | null]> | undefined,
): XYPoint[] {
  if (!series) return [];
  return series.map(([d, v]) => ({ x: d, y: v }));
}

// Round to max 2 decimals so axis ticks don't show floating-point artifacts
// like 5.6000000000000005%.
function r2(v: number | null | undefined): number | null | undefined {
  if (v == null || !isFinite(v)) return v;
  return Math.round(v * 100) / 100;
}

function r2str(v: number | null | undefined): string {
  const r = r2(v);
  return r == null ? "" : String(r);
}

function baseLineOptions(opts: BaseLineOptionsArgs = {}) {
  const palette = buildPalette();
  const yTickCallback = opts.yTicks?.callback;

  return {
    responsive: true,
    maintainAspectRatio: false,
    // prefers-reduced-motion: reduce means Chart.js's own rAF-driven draw
    // animation, not just CSS transitions — a global CSS kill switch can't
    // touch this loop, so BriefChart.tsx reads the media query and threads
    // it through BuildContext.reducedMotion into every builder.
    animation: opts.reducedMotion ? false : { duration: 300 },
    interaction: { mode: "index" as const, intersect: false },
    spanGaps: true,
    elements: {
      line: { tension: 0.3, borderJoinStyle: "round" as const },
      point: {
        radius: 0,
        hoverRadius: 4,
        hoverBorderWidth: 2,
        hoverBackgroundColor: palette.paper,
      },
    },
    plugins: {
      legend: opts.legend
        ? {
            display: true,
            position: "top" as const,
            align: "end" as const,
            labels: {
              usePointStyle: true,
              boxWidth: 8,
              font: FONT,
              color: palette.ink2,
            },
          }
        : { display: false },
      tooltip: {
        backgroundColor: palette.ink,
        titleColor: palette.paper,
        bodyColor: palette.paper,
        titleFont: { size: 11, weight: "bold" as const, family: FONT.family },
        bodyFont: { size: 11, family: FONT.family },
        padding: 10,
        usePointStyle: true,
        boxPadding: 4,
        cornerRadius: 2,
        callbacks: {
          label: (ctx: { parsed: { y: number | null }; dataset: { label?: string } }) => {
            const v = ctx.parsed.y;
            const label = ctx.dataset.label || "";
            if (v == null) return label ? label + ": —" : "—";
            const fmt = yTickCallback
              ? yTickCallback(v)
              : Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
            return label ? label + ": " + fmt : String(fmt);
          },
        },
      },
    },
    scales: {
      x: {
        type: "time" as const,
        time: { unit: "year" as const, tooltipFormat: "MMM yyyy" },
        grid: { color: palette.ruleFaint },
        ticks: { color: palette.ink3, font: FONT },
      },
      y: {
        grid: { color: palette.ruleFaint },
        ticks: {
          color: palette.ink3,
          font: FONT,
          ...(opts.yTicks ?? {}),
        },
      },
    },
  };
}

// Empty/safe config — returned when a chart has no data so Chart.js renders
// a blank frame instead of crashing.
function emptyLineConfig(): ChartConfiguration<"line"> {
  return {
    type: "line",
    data: { datasets: [] },
    options: baseLineOptions(),
  } as unknown as ChartConfiguration<"line">;
}

function emptyBarConfig(): ChartConfiguration<"bar"> {
  return {
    type: "bar",
    data: { datasets: [] },
    options: baseLineOptions(),
  } as unknown as ChartConfiguration<"bar">;
}

function hasAnyData(series: SeriesByKey, keys: string[]): boolean {
  return keys.some((k) => Array.isArray(series[k]) && series[k].length > 0);
}

// ----------------------------------------------------------------------
// Event-markers plugin (DSEX) — ported from EconDelta's
// makeEventMarkersPlugin. Renders a colored ring above the chart for each
// event with a dashed drop line; on hover the line goes solid and a
// labelled box appears above the ring.
// ----------------------------------------------------------------------

function makeEventMarkersPlugin(
  events: EventMarker[],
  palette: Palette,
): Plugin<"line"> {
  return {
    id: "eventMarkers",
    afterDatasetsDraw(chart: ChartType<"line">) {
      const c = chart as ChartWithHoverIdx;
      const ctx = c.ctx;
      const chartArea: ChartArea | undefined = c.chartArea;
      if (!chartArea) return;
      const xs = c.scales.x as Scale | undefined;
      if (!xs) return;
      const dotY = chartArea.top - 14;
      const hovered = c.$hoveredMarkerIdx ?? null;

      ctx.save();

      events.forEach((e, i) => {
        const xPx = xs.getPixelForValue(new Date(e.date).getTime());
        if (xPx < chartArea.left - 10 || xPx > chartArea.right + 10) return;
        const isHovered = hovered === i;

        // Vertical drop line (dashed, or solid when hovered)
        ctx.strokeStyle = e.color;
        ctx.globalAlpha = isHovered ? 0.85 : 0.3;
        ctx.lineWidth = isHovered ? 1.4 : 0.9;
        ctx.setLineDash(isHovered ? [] : [3, 3]);
        ctx.beginPath();
        ctx.moveTo(xPx, dotY + 3);
        ctx.lineTo(xPx, chartArea.bottom);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;

        // Outer colored ring
        const capR = isHovered ? 6 : 4;
        ctx.fillStyle = e.color;
        ctx.beginPath();
        ctx.arc(xPx, dotY, capR, 0, Math.PI * 2);
        ctx.fill();
        // Inner paper dot — reads as a ring
        ctx.fillStyle = palette.paper;
        ctx.beginPath();
        ctx.arc(xPx, dotY, isHovered ? 2.4 : 1.6, 0, Math.PI * 2);
        ctx.fill();
      });

      // Hovered label box + connector + date string
      if (hovered != null && events[hovered]) {
        const e = events[hovered];
        const xPx = xs.getPixelForValue(new Date(e.date).getTime());
        if (xPx >= chartArea.left - 10 && xPx <= chartArea.right + 10) {
          const titleText = (e.title || "").toUpperCase();
          ctx.font = `600 10px ${FONT.family}`;
          const textW = ctx.measureText(titleText).width;
          const padX = 10;
          const w = textW + padX * 2;
          const h = 22;
          let labelX = xPx - w / 2;
          if (labelX < chartArea.left) labelX = chartArea.left + 4;
          if (labelX + w > chartArea.right) labelX = chartArea.right - w - 4;
          const labelY = dotY - h - 12;

          // Connector
          ctx.strokeStyle = e.color;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.moveTo(xPx, dotY - 6);
          ctx.lineTo(xPx, labelY + h);
          ctx.stroke();

          // Filled box
          ctx.fillStyle = e.color;
          ctx.strokeStyle = e.color;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.rect(labelX, labelY, w, h);
          ctx.fill();
          ctx.stroke();

          // Title text
          ctx.fillStyle = palette.paper;
          ctx.textBaseline = "middle";
          ctx.fillText(titleText, labelX + padX, labelY + h / 2);

          // Date string
          ctx.font = `10px ${FONT.family}`;
          ctx.fillStyle = e.color;
          const dateStr = new Date(e.date)
            .toLocaleDateString("en-US", { year: "numeric", month: "short" })
            .toUpperCase();
          const dateW = ctx.measureText(dateStr).width;
          let dateX = xPx - dateW / 2;
          if (dateX < chartArea.left) dateX = chartArea.left + 4;
          if (dateX + dateW > chartArea.right) dateX = chartArea.right - dateW - 4;
          ctx.fillText(dateStr, dateX, dotY + 14);
        }
      }

      ctx.restore();
    },
    afterEvent(chart, args) {
      const c = chart as ChartWithHoverIdx;
      const ev: ChartEvent = args.event;
      if (!ev || (ev.type !== "mousemove" && ev.type !== "mouseout")) return;
      const chartArea = c.chartArea;
      if (!chartArea) return;
      const dotY = chartArea.top - 14;
      const xs = c.scales.x as Scale | undefined;
      if (!xs) return;
      let nearest: number | null = null;
      let nearestDist = Infinity;
      const evY = ev.y ?? -1;
      const evX = ev.x ?? -1;
      const inZone =
        ev.type === "mousemove" && evY >= dotY - 18 && evY <= dotY + 18;
      if (inZone) {
        events.forEach((e, i) => {
          const xPx = xs.getPixelForValue(new Date(e.date).getTime());
          const d = Math.abs(xPx - evX);
          if (d < nearestDist) {
            nearestDist = d;
            nearest = i;
          }
        });
        if (nearestDist > 18) nearest = null;
      }
      if (nearest !== c.$hoveredMarkerIdx) {
        c.$hoveredMarkerIdx = nearest;
        args.changed = true;
      }
      // No pointer cursor — markers aren't clickable. Hover-only feedback
      // comes from the label box that pops above the marker.
    },
  };
}

// Map SectionV6 notes → event markers. The brief only has one tone-per-event
// (vs. EconDelta's hardcoded color); use the accent for now and let
// upstream extend later via SeriesNote.detail/tone if needed.
function notesToEvents(
  notes: SeriesNote[] | undefined,
  seriesKey: string,
  defaultColor: string,
): EventMarker[] {
  if (!notes) return [];
  return notes
    .filter((n) => n.series_key === seriesKey && n.ts && n.label)
    .map((n) => ({
      date: n.ts,
      title: n.label,
      color: defaultColor,
    }));
}

// ----------------------------------------------------------------------
// Chart-config builders (5 for Phase E.1 Option A)
// ----------------------------------------------------------------------

/**
 * fxFlows — stacked bar of monthly export / remittance / import flows.
 * Inflows (export, remittance) stack positive; imports plotted negative.
 */
function fxFlowsConfig(ctx: BuildContext): ChartConfiguration<"bar"> {
  const keys = ["monthly_export", "monthly_remittance", "monthly_import"];
  if (!hasAnyData(ctx.series, keys)) return emptyBarConfig();

  const palette = buildPalette();
  const exp = toPoints(ctx.series["monthly_export"]);
  const rem = toPoints(ctx.series["monthly_remittance"]);
  const imp = (ctx.series["monthly_import"] || []).map(([d, v]) => ({
    x: d,
    y: v == null ? null : -Math.abs(v),
  }));

  const datasets: ChartDataset<"bar", XYPoint[]>[] = [
    {
      label: "Exports",
      data: exp,
      backgroundColor: palette.bull,
      borderWidth: 0,
      stack: "inflow",
    },
    {
      label: "Remittance",
      data: rem,
      backgroundColor: palette.ink2,
      borderWidth: 0,
      stack: "inflow",
    },
    {
      label: "Imports (–)",
      data: imp,
      backgroundColor: palette.bear,
      borderWidth: 0,
      stack: "outflow",
    },
  ];

  const base = baseLineOptions({ reducedMotion: ctx.reducedMotion, legend: true });
  // Stacked bars across both axes
  const options = {
    ...base,
    scales: {
      ...base.scales,
      x: { ...base.scales.x, stacked: true, time: { unit: "month" as const, tooltipFormat: "MMM yyyy" } },
      y: { ...base.scales.y, stacked: true },
    },
  };

  return {
    type: "bar",
    data: { datasets },
    options,
  } as unknown as ChartConfiguration<"bar">;
}

/**
 * fxBalance — F3. External Flow Balance for §fx (FIG.01). Diverging area +
 * bold net-balance line, 24-month, USD bn, read from metric_history_monthly.
 * Inflows (exports + remittance) stack UP via manual cumulative values
 * (remittance dataset = exports+remittance, fill:"-1"); imports drawn as a
 * negative area; net = exports+remittance-imports is the hero line.
 *
 * AGENTS.md landmine: do NOT use scales.y.stacked here — it folds the negative
 * imports area + the overlay net line into the stack and renders wrong. Stack
 * inflows manually (caught in the F3 brainstorm mockup: inflows showed ~$4bn
 * instead of ~$7bn under y.stacked). TimeScale already registered in
 * BriefChart.tsx (landmine #2).
 *
 * Area fills: the brief's fill convention is a low-alpha variant of the line's
 * hue (see brentConfig/lngConfig → palette.accentSoft, an oklch-with-alpha CSS
 * var). There is no `rgba`/`withAlpha` util in this codebase, and the bull/bear/
 * ink2 tokens are solid (opaque) inks — drawn as overlapping areas they'd
 * occlude each other and the hero net line. So the three diverging areas use a
 * native color-mix() soft tint derived from the SAME --bull/--bear/--ink-2
 * tokens (≈18%, mirroring accentSoft's ~12%); borders stay the solid ink so
 * each band keeps a crisp edge, and the net line stays solid palette.ink.
 */
function fxBalanceConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const EXP = "exports_usd_mn_monthly";
  const IMP = "imports_usd_mn_monthly";
  const REM = "remittance_usd_mn_monthly";
  if (!hasAnyData(ctx.series, [EXP, IMP, REM])) return emptyLineConfig();

  const palette = buildPalette();
  // Low-alpha tint of a solid ink, reusing the same hue (mirrors accentSoft).
  const AREA_ALPHA = 18; // mirrors accentSoft (~12%), nudged up for diverging-area legibility
  const soft = (ink: string): string => `color-mix(in oklch, ${ink} ${AREA_ALPHA}%, transparent)`;

  // mn → bn, aligned by ts.
  const toBn = (key: string): XYPoint[] =>
    toPoints(ctx.series[key]).map((p) => ({ x: p.x, y: p.y == null ? null : p.y / 1000 }));
  const exp = toBn(EXP);
  const imp = toBn(IMP);
  const rem = toBn(REM);
  const remByTs = new Map(rem.map((p) => [p.x, p.y]));
  const impByTs = new Map(imp.map((p) => [p.x, p.y]));
  // A missing month in any component yields null (no fabricated 0 / fake zero-crossing).
  // spanGaps (from baseLineOptions) bridges the LINE across it, but no false value is plotted.
  const inflowTop: XYPoint[] = exp.map((p) => {
    const r = remByTs.get(p.x);
    return { x: p.x, y: p.y == null || r == null ? null : p.y + r };
  });
  const net: XYPoint[] = exp.map((p) => {
    const r = remByTs.get(p.x);
    const m = impByTs.get(p.x);
    return { x: p.x, y: p.y == null || r == null || m == null ? null : p.y + r - m };
  });
  const impNeg: XYPoint[] = imp.map((p) => ({ x: p.x, y: p.y == null ? null : -Math.abs(p.y) }));

  // Per-series dimming (H6): worst-of is right for DETECTING that this chart
  // needs a closer look, but wrong for drawing it — verified live, the
  // imports line here can stop (Mar 2026) while exports/remittance keep
  // updating, and blanket-dimming the whole canvas would mute two current
  // lines to signal one dead one. Only the flagged key's own line dims; the
  // derived "Net basic balance" line dims too if ANY of its three inputs is
  // stale, since it's a function of all three and can't be more current
  // than its oldest input.
  const isStale = (key: string) => ctx.staleKeys?.has(key) ?? false;
  const netStale = isStale(EXP) || isStale(IMP) || isStale(REM);

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "Exports",
      data: exp,
      backgroundColor: isStale(EXP) ? dimColor(palette.bull) : soft(palette.bull),
      borderColor: isStale(EXP) ? dimColor(palette.bull) : palette.bull,
      borderWidth: 0.8,
      fill: "origin",
      pointRadius: 0,
      tension: 0.3,
    },
    {
      label: "Remittance",
      data: inflowTop,
      backgroundColor: isStale(REM) ? dimColor(palette.ink2) : soft(palette.ink2),
      borderColor: isStale(REM) ? dimColor(palette.ink2) : palette.ink2,
      borderWidth: 0.8,
      fill: "-1",
      pointRadius: 0,
      tension: 0.3,
    },
    {
      label: "Imports",
      data: impNeg,
      backgroundColor: isStale(IMP) ? dimColor(palette.bear) : soft(palette.bear),
      borderColor: isStale(IMP) ? dimColor(palette.bear) : palette.bear,
      borderWidth: 0.8,
      fill: "origin",
      pointRadius: 0,
      tension: 0.3,
    },
    {
      label: "Net basic balance",
      data: net,
      borderColor: netStale ? dimColor(palette.ink) : palette.ink,
      borderWidth: 2.6,
      fill: false,
      pointRadius: 0,
      tension: 0.25,
      order: 0,
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    legend: true,
    yTicks: { callback: (v: number) => (v < 0 ? "-$" : "$") + r2str(Math.abs(v)) },
  });

  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: {
          ...baseOpts.scales.x,
          time: { unit: "month" as const, tooltipFormat: "MMM yyyy" },
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 9 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

/**
 * dsex — single-line DSEX index with event markers above the data area.
 * Events sourced from `ctx.notes` filtered to series_key === 'dsex'.
 */
function dsexConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const seriesKey = "dsex";
  if (!hasAnyData(ctx.series, [seriesKey])) return emptyLineConfig();

  const palette = buildPalette();
  const dataPts = toPoints(ctx.series[seriesKey]);
  const events = notesToEvents(ctx.notes, seriesKey, palette.accent).filter(
    (e) => !!e.color && !!e.date,
  );

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion, legend: false });
  const options = {
    ...baseOpts,
    layout: events.length > 0 ? { padding: { top: 50 } } : {},
    interaction: { mode: "index" as const, intersect: false },
    scales: {
      ...baseOpts.scales,
      x: { ...baseOpts.scales.x, time: { unit: "day" as const, tooltipFormat: "MMM d" } },
    },
  };

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "DSEX",
      data: dataPts,
      borderColor: palette.ink,
      backgroundColor: palette.ruleFaint,
      borderWidth: 1.4,
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0.25,
      fill: false,
    },
  ];

  return {
    type: "line",
    data: { datasets },
    options,
    plugins: events.length > 0 ? [makeEventMarkersPlugin(events, palette)] : [],
  } as unknown as ChartConfiguration<"line">;
}

/**
 * brent — single-line Brent crude oil price (USD/bbl) with hero-area fill.
 * The brief uses this on the Iran section as a dramatic single line.
 */
function brentConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const seriesKey = "brent";
  if (!hasAnyData(ctx.series, [seriesKey])) return emptyLineConfig();

  const palette = buildPalette();
  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "Brent",
      data: toPoints(ctx.series[seriesKey]),
      borderColor: palette.accent,
      backgroundColor: palette.accentSoft,
      borderWidth: 2,
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0.2,
      fill: "origin",
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    yTicks: { callback: (v: number) => "$" + r2str(v) },
  });
  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: { ...baseOpts.scales.x, time: { unit: "day" as const, tooltipFormat: "MMM d" } },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

/**
 * yieldCurve — BD govt yield curve. Category x-axis (3M/6M/1Y/5Y/10Y) with
 * equal spacing per V3 reference. Two datasets: latest (solid accent) and
 * one prior (dashed) for week-over-week term-structure shift.
 */
function yieldCurveConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const tenorMap: Array<{ id: string; label: string }> = [
    { id: "yield_3m", label: "3M" },
    { id: "yield_6m", label: "6M" },
    { id: "yield_1y", label: "1Y" },
    { id: "yield_5y", label: "5Y" },
    { id: "yield_10y", label: "10Y" },
  ];
  const labels: string[] = tenorMap.map((t) => t.label);

  if (!hasAnyData(
    ctx.series,
    tenorMap.map((t) => t.id),
  )) {
    return emptyLineConfig();
  }

  const palette = buildPalette();
  // For each as_of date, build a tenor-aligned y-array with null for missing points.
  // Category axis means dataset.data is positional: index N corresponds to labels[N].
  const byDate: Record<string, Array<number | null>> = {};
  tenorMap.forEach((t, idx) => {
    (ctx.series[t.id] || []).forEach(([d, v]) => {
      if (!byDate[d]) byDate[d] = Array(tenorMap.length).fill(null);
      byDate[d][idx] = v;
    });
  });
  const dates = Object.keys(byDate).sort();
  if (!dates.length) return emptyLineConfig();

  // V3-aligned: show latest + 1 prior only (dashed). Older snapshots in the
  // data may have partial-tenor coverage and clutter the chart.
  const latest = dates[dates.length - 1];
  const prior = dates.length > 1 ? dates[dates.length - 2] : null;

  const datasets: ChartDataset<"line", Array<number | null>>[] = [];
  if (prior) {
    datasets.push({
      label: shortDate(prior),
      data: byDate[prior],
      borderColor: palette.ruleSoft,
      backgroundColor: palette.ruleSoft,
      borderWidth: 1.4,
      borderDash: [4, 4],
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0.1,
      showLine: true,
      spanGaps: true,
    });
  }
  datasets.push({
    label: shortDate(latest),
    data: byDate[latest],
    borderColor: palette.accent,
    backgroundColor: palette.accent,
    borderWidth: 2.5,
    pointRadius: 4,
    pointHoverRadius: 6,
    tension: 0.1,
    showLine: true,
    spanGaps: true,
  });

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: ctx.reducedMotion ? false : { duration: 300 },
    interaction: { mode: "nearest" as const, intersect: false, axis: "x" as const },
    elements: {
      line: { tension: 0.1, borderJoinStyle: "round" as const },
      point: {
        hoverRadius: 5,
        hoverBorderWidth: 2,
        hoverBackgroundColor: palette.paper,
      },
    },
    plugins: {
      legend: {
        display: true,
        position: "top" as const,
        align: "end" as const,
        labels: {
          usePointStyle: true,
          boxWidth: 8,
          font: FONT,
          color: palette.ink2,
        },
      },
      tooltip: {
        backgroundColor: palette.ink,
        titleColor: palette.paper,
        bodyColor: palette.paper,
        titleFont: { size: 11, weight: "bold" as const, family: FONT.family },
        bodyFont: { size: 11, family: FONT.family },
        padding: 10,
        cornerRadius: 2,
        callbacks: {
          title: (items: Array<{ dataset: { label?: string } }>) =>
            items[0]?.dataset.label ?? "",
          label: (ctxPt: { parsed: { x: number; y: number }; label?: string }) => {
            const tenorLabel = ctxPt.label ?? labels[ctxPt.parsed.x] ?? "";
            return tenorLabel + ": " + Number(ctxPt.parsed.y).toFixed(2) + "%";
          },
        },
      },
    },
    scales: {
      x: {
        type: "category" as const,
        title: { display: true, text: "Tenor", font: FONT, color: palette.ink3 },
        grid: { color: palette.ruleFaint },
        ticks: { color: palette.ink3, font: FONT },
      },
      y: {
        ticks: {
          color: palette.ink3,
          font: FONT,
          callback: (v: number | string) => r2str(typeof v === "number" ? v : Number(v)) + "%",
        },
        grid: { color: palette.ruleFaint },
      },
    },
  };

  return {
    type: "line",
    data: { labels, datasets },
    options,
  } as unknown as ChartConfiguration<"line">;
}

/**
 * yieldLadder — F5. Full 8-tenor BD govt yield ladder (91D · 182D · 364D · 2Y ·
 * 5Y · 10Y · 15Y · 20Y) over the last 2 month-ends, read from
 * metric_history_monthly. Replaces the daily 5-point yieldCurve on §tbond
 * (FIG.03) with the full term structure plus month-over-month shift.
 *
 * Category x-axis (tenor), latest month-end solid (accent), prior dashed —
 * mirrors yieldCurveConfig. CategoryScale is already registered in
 * BriefChart.tsx per AGENTS.md landmine #2 (no new registration needed).
 */
function yieldLadderConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const tenorMap: Array<{ id: string; label: string }> = [
    { id: "tbill_91d_yield_monthly", label: "91D" },
    { id: "tbill_182d_yield_monthly", label: "182D" },
    { id: "tbill_364d_yield_monthly", label: "364D" },
    { id: "yield_2y_monthly", label: "2Y" },
    { id: "yield_5y_monthly", label: "5Y" },
    { id: "yield_10y_monthly", label: "10Y" },
    { id: "yield_15y_monthly", label: "15Y" },
    { id: "yield_20y_monthly", label: "20Y" },
  ];
  const labels: string[] = tenorMap.map((t) => t.label);

  if (!hasAnyData(
    ctx.series,
    tenorMap.map((t) => t.id),
  )) {
    return emptyLineConfig();
  }

  const palette = buildPalette();
  // For each as_of date, build a tenor-aligned y-array with null for missing points.
  // Category axis means dataset.data is positional: index N corresponds to labels[N].
  const byDate: Record<string, Array<number | null>> = {};
  tenorMap.forEach((t, idx) => {
    (ctx.series[t.id] || []).forEach(([d, v]) => {
      if (!byDate[d]) byDate[d] = Array(tenorMap.length).fill(null);
      byDate[d][idx] = v;
    });
  });
  const dates = Object.keys(byDate).sort();
  if (!dates.length) return emptyLineConfig();

  // Show the last 2 month-ends only: latest (solid accent) + 1 prior (dashed).
  const latest = dates[dates.length - 1];
  const prior = dates.length > 1 ? dates[dates.length - 2] : null;

  const datasets: ChartDataset<"line", Array<number | null>>[] = [];
  if (prior) {
    datasets.push({
      label: monthLabel(prior),
      data: byDate[prior],
      borderColor: palette.ruleSoft,
      backgroundColor: palette.ruleSoft,
      borderWidth: 1.4,
      borderDash: [4, 4],
      pointRadius: 2,
      pointHoverRadius: 4,
      tension: 0.1,
      showLine: true,
      spanGaps: true,
    });
  }
  datasets.push({
    label: monthLabel(latest),
    data: byDate[latest],
    borderColor: palette.accent,
    backgroundColor: palette.accent,
    borderWidth: 2.5,
    pointRadius: 4,
    pointHoverRadius: 6,
    tension: 0.1,
    showLine: true,
    spanGaps: true,
  });

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: ctx.reducedMotion ? false : { duration: 300 },
    interaction: { mode: "nearest" as const, intersect: false, axis: "x" as const },
    elements: {
      line: { tension: 0.1, borderJoinStyle: "round" as const },
      point: {
        hoverRadius: 5,
        hoverBorderWidth: 2,
        hoverBackgroundColor: palette.paper,
      },
    },
    plugins: {
      legend: {
        display: true,
        position: "top" as const,
        align: "end" as const,
        labels: {
          usePointStyle: true,
          boxWidth: 8,
          font: FONT,
          color: palette.ink2,
        },
      },
      tooltip: {
        backgroundColor: palette.ink,
        titleColor: palette.paper,
        bodyColor: palette.paper,
        titleFont: { size: 11, weight: "bold" as const, family: FONT.family },
        bodyFont: { size: 11, family: FONT.family },
        padding: 10,
        cornerRadius: 2,
        callbacks: {
          title: (items: Array<{ dataset: { label?: string } }>) =>
            items[0]?.dataset.label ?? "",
          label: (ctxPt: { parsed: { x: number; y: number }; label?: string }) => {
            const tenorLabel = ctxPt.label ?? labels[ctxPt.parsed.x] ?? "";
            return tenorLabel + ": " + Number(ctxPt.parsed.y).toFixed(2) + "%";
          },
        },
      },
    },
    scales: {
      x: {
        type: "category" as const,
        title: { display: true, text: "Tenor", font: FONT, color: palette.ink3 },
        grid: { color: palette.ruleFaint },
        ticks: { color: palette.ink3, font: FONT },
      },
      y: {
        ticks: {
          color: palette.ink3,
          font: FONT,
          callback: (v: number | string) => r2str(typeof v === "number" ? v : Number(v)) + "%",
        },
        grid: { color: palette.ruleFaint },
      },
    },
  };

  return {
    type: "line",
    data: { labels, datasets },
    options,
  } as unknown as ChartConfiguration<"line">;
}

/**
 * cpiTrend — 24-month CPI line chart with 3 datasets.
 *
 * Reads three monthly series from section.series:
 *   cpi_12m_avg_monthly   (headline 12-month average)
 *   cpi_p2p_food_monthly  (food P-to-P)
 *   cpi_p2p_nonfood_monthly (non-food P-to-P)
 *
 * Y-axis = percent. X-axis = TimeScale (already registered in BriefChart.tsx
 * per AGENTS.md landmine #2 — no new registration needed).
 */
function cpiTrendConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const HEADLINE_KEY = "cpi_12m_avg_monthly";
  const FOOD_KEY = "cpi_p2p_food_monthly";
  const NONFOOD_KEY = "cpi_p2p_nonfood_monthly";

  if (!hasAnyData(ctx.series, [HEADLINE_KEY, FOOD_KEY, NONFOOD_KEY])) {
    return emptyLineConfig();
  }

  const palette = buildPalette();
  const isStale = (key: string) => ctx.staleKeys?.has(key) ?? false;

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "Headline (12m avg)",
      data: toPoints(ctx.series[HEADLINE_KEY]),
      borderColor: isStale(HEADLINE_KEY) ? dimColor(palette.ink) : palette.ink,
      borderWidth: 1.8,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
    {
      label: "Food (P-to-P)",
      data: toPoints(ctx.series[FOOD_KEY]),
      borderColor: isStale(FOOD_KEY) ? dimColor(palette.warn) : palette.warn,
      borderWidth: 1.2,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
    {
      label: "Non-Food (P-to-P)",
      data: toPoints(ctx.series[NONFOOD_KEY]),
      borderColor: isStale(NONFOOD_KEY) ? dimColor(palette.ink3) : palette.ink3,
      borderWidth: 1.2,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    legend: true,
    yTicks: { callback: (v: number) => r2str(v) + "%" },
  });

  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: {
          ...baseOpts.scales.x,
          time: { unit: "month" as const, tooltipFormat: "MMM yyyy" },
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 8 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

/**
 * remitFlow — 12-month monthly remittance inflow line (USD mn) for §08.
 *
 * Reads remittance_usd_mn_monthly from section.series. Single-series,
 * newspaper-thin (mirrors the cpiTrend treatment). Y-axis = USD mn,
 * X-axis = monthly TimeScale (registered in BriefChart.tsx per landmine #2).
 *
 * NB: the §08 KPI headline ($3,130mn) comes from the daily-tracked
 * remit_monthly_mn series; this chart plots a different BB monthly vintage
 * (remittance_usd_mn_monthly), so its latest point may differ — the subtitle
 * flags the monthly basis so a banker doesn't read it as a discrepancy.
 */
function remitFlowConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const KEY = "remittance_usd_mn_monthly";

  if (!hasAnyData(ctx.series, [KEY])) {
    return emptyLineConfig();
  }

  const palette = buildPalette();

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "Remittance (monthly)",
      data: toPoints(ctx.series[KEY]),
      borderColor: palette.ink,
      borderWidth: 1.8,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    legend: false,
    yTicks: { callback: (v: number) => Number(v).toLocaleString() },
  });

  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: {
          ...baseOpts.scales.x,
          time: { unit: "month" as const, tooltipFormat: "MMM yyyy" },
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 8 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

/**
 * fiscalNbr — F7b. ~28-month monthly NBR tax-revenue line (BDT crore) for
 * §fiscal. Reads nbr_revenue_monthly_cr from section.series. Single-series,
 * newspaper-thin (mirrors remitFlow). Y-axis = BDT crore, X-axis = monthly
 * TimeScale (already registered in BriefChart.tsx per AGENTS.md landmine #2).
 *
 * NB: the §fiscal headline cards ("NBR collected YTD") come from a different
 * external pipeline (fiscal_*_trn, YTD); this chart plots EconDelta's
 * single-MONTH figures, so its scale/latest differ by design — the subtitle
 * flags the monthly basis.
 */
function fiscalNbrConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const KEY = "nbr_revenue_monthly_cr";

  if (!hasAnyData(ctx.series, [KEY])) {
    return emptyLineConfig();
  }

  const palette = buildPalette();

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "NBR revenue (monthly)",
      data: toPoints(ctx.series[KEY]),
      borderColor: palette.ink,
      borderWidth: 1.8,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    legend: false,
    yTicks: { callback: (v: number) => Number(v).toLocaleString() },
  });

  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: {
          ...baseOpts.scales.x,
          time: { unit: "month" as const, tooltipFormat: "MMM yyyy" },
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 8 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

/**
 * reserves — F2. 13-month gross + net (BPM6) foreign-exchange reserves
 * two-line (USD bn) for §02 Policy & Rates (slug `bb`).
 *
 * Reads gross_reserves_usd_bn_monthly + net_reserves_bpm6_usd_bn_monthly from
 * section.series. Mirrors cpiTrend (multi-dataset monthly time-line). Y-axis =
 * USD bn, X-axis = monthly TimeScale (registered in BriefChart.tsx per
 * AGENTS.md landmine #2 — no new registration needed).
 *
 * NB: the gross/net gap is BB's reported reserve-asset buffer minus BPM6
 * adjustments (ACU, swaps); the legend labels keep both lines distinct.
 */
function reservesConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const GROSS_KEY = "gross_reserves_usd_bn_monthly";
  const BPM6_KEY = "net_reserves_bpm6_usd_bn_monthly";

  if (!hasAnyData(ctx.series, [GROSS_KEY, BPM6_KEY])) {
    return emptyLineConfig();
  }

  const palette = buildPalette();
  const isStale = (key: string) => ctx.staleKeys?.has(key) ?? false;

  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "Gross",
      data: toPoints(ctx.series[GROSS_KEY]),
      borderColor: isStale(GROSS_KEY) ? dimColor(palette.ink) : palette.ink,
      borderWidth: 1.8,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
    {
      label: "Net (BPM6)",
      data: toPoints(ctx.series[BPM6_KEY]),
      borderColor: isStale(BPM6_KEY) ? dimColor(palette.accent) : palette.accent,
      borderWidth: 1.4,
      pointRadius: 0,
      tension: 0.25,
      fill: false,
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    legend: true,
    yTicks: { callback: (v: number) => r2str(v) },
  });

  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: {
          ...baseOpts.scales.x,
          time: { unit: "month" as const, tooltipFormat: "MMM yyyy" },
          ticks: { ...baseOpts.scales.x.ticks, maxTicksLimit: 8 },
        },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

// Format a YYYY-MM-DD date string as "MMM DD" (e.g. "May 09"). Falls back
// to the input on any parse mismatch.
function shortDate(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthIdx = parseInt(m[2], 10) - 1;
  if (monthIdx < 0 || monthIdx > 11) return iso;
  return `${months[monthIdx]} ${m[3]}`;
}

// Format a YYYY-MM-DD date string as "MMM yyyy" (e.g. "Apr 2026"). Used for
// monthly-snapshot dataset labels (yieldLadder). Falls back to the input.
function monthLabel(iso: string): string {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return iso;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthIdx = parseInt(m[2], 10) - 1;
  if (monthIdx < 0 || monthIdx > 11) return iso;
  return `${months[monthIdx]} ${m[1]}`;
}

/**
 * lng — single-line LNG JKM price ($/MMBtu) for the commodities section.
 * Newspaper-thin without area fill (dramatic but understated; LNG is a
 * smaller-tile commodity in this issue, so brent owns the hero treatment).
 */
function lngConfig(ctx: BuildContext): ChartConfiguration<"line"> {
  const seriesKey = "lng_jkm";
  if (!hasAnyData(ctx.series, [seriesKey])) return emptyLineConfig();

  const palette = buildPalette();
  const datasets: ChartDataset<"line", XYPoint[]>[] = [
    {
      label: "LNG JKM",
      data: toPoints(ctx.series[seriesKey]),
      borderColor: palette.accent,
      backgroundColor: palette.accentSoft,
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.2,
      fill: "origin",
    },
  ];

  const baseOpts = baseLineOptions({ reducedMotion: ctx.reducedMotion,
    yTicks: { callback: (v: number) => "$" + r2str(v) + "/MMBtu" },
  });
  return {
    type: "line",
    data: { datasets },
    options: {
      ...baseOpts,
      scales: {
        ...baseOpts.scales,
        x: { ...baseOpts.scales.x, time: { unit: "month" as const, tooltipFormat: "MMM yyyy" } },
      },
    },
  } as unknown as ChartConfiguration<"line">;
}

// ----------------------------------------------------------------------
// Registry
// ----------------------------------------------------------------------

// All builders return ChartConfiguration of varying chart types — narrow at
// the call site via the configKey lookup, since each builder's return type
// is precise.
type AnyChartConfig =
  | ChartConfiguration<"line">
  | ChartConfiguration<"bar">;

export const chartConfigs = {
  fxFlows: fxFlowsConfig,
  fxBalance: fxBalanceConfig,
  dsex: dsexConfig,
  brent: brentConfig,
  yieldCurve: yieldCurveConfig,
  yieldLadder: yieldLadderConfig,
  lng: lngConfig,
  cpiTrend: cpiTrendConfig,
  remitFlow: remitFlowConfig,
  reserves: reservesConfig,
  fiscalNbr: fiscalNbrConfig,
} as const;

export type ChartConfigKey = keyof typeof chartConfigs;

export type ChartConfigBuilder = (ctx: BuildContext) => AnyChartConfig;

// Convenience: section slug → which chart key to render.
// Section.tsx (Phase E.3) will look up by section.slug.
export const SECTION_TO_CHART: Partial<Record<string, ChartConfigKey>> = {
  bb: "reserves",
  fx: "fxBalance",
  dse: "dsex",
  iran: "brent",
  tbond: "yieldLadder",
  comm: "lng",
  macro: "cpiTrend",
  remit: "remitFlow",
  fiscal: "fiscalNbr",
};

// Per-chart card-head metadata — mirrors EconDelta /macro's FIG.NN + title
// + subtitle pattern.
//
// `fig` here is NOT what renders anymore. It used to be — assigned in
// chart-addition order (fx=01, dse=02, tbond=03, comm=04, iran=05, macro=06,
// remit=07, bb=08, fiscal=09) — which meant the printed sequence followed
// the order charts were ADDED to this file, not the order sections actually
// render in, so a reader saw "FIG.08, 01, 02, 03, 06, 07, 09, 05" top to
// bottom with no FIG.04 (comm was retired, landmine 30). ClientApp.tsx now
// computes a `chartOrd` per slug from the real render order and Section.tsx
// uses that; `fig` is kept only as a defensive fallback for a charted
// section this table hasn't been told the render position of.
export interface ChartCardHead {
  fig: string;
  title: string;
  subtitle?: string;
}

export const CHART_CARD_HEADS: Partial<Record<string, ChartCardHead>> = {
  bb: {
    fig: "08",
    title: "FX Reserves",
    subtitle: "13-month · gross + net (BPM6) · USD bn",
  },
  fx: {
    fig: "01",
    title: "External Flow Balance",
    subtitle: "24-month · inflows vs imports · net basic balance · USD bn",
  },
  dse: {
    fig: "02",
    title: "DSEX Index",
    subtitle: "Daily close",
  },
  tbond: {
    fig: "03",
    title: "BD Govt Yield Ladder",
    subtitle: "8-tenor · last 2 months · 91D to 20Y",
  },
  comm: {
    fig: "04",
    title: "LNG JKM",
    subtitle: "Weekly · USD/MMBtu",
  },
  iran: {
    fig: "05",
    title: "Brent Crude",
    subtitle: "Daily · USD/bbl",
  },
  macro: {
    fig: "06",
    title: "CPI Trend",
    subtitle: "24-month · headline 12m-avg · food · non-food",
  },
  remit: {
    fig: "07",
    title: "Remittance Inflow",
    subtitle: "12-month · monthly · USD mn",
  },
  fiscal: {
    fig: "09",
    title: "NBR Tax Revenue",
    subtitle: "Monthly · BDT crore",
  },
};

// Internal exports — used by tests & BriefChart wrapper. Not part of the
// public API surface for Section.tsx.
export const __internals = {
  buildPalette,
  cssVar,
  toPoints,
  r2,
  baseLineOptions,
  makeEventMarkersPlugin,
  notesToEvents,
};

// Re-export Chart.js types we forward — saves callers from importing both
// our module and chart.js directly.
export type { ChartConfiguration, ChartJSType };
