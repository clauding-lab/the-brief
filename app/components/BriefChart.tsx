"use client";

// THE BRIEF — Chart.js React wrapper.
//
// Takes a SectionV6 and a ChartConfigKey, groups the section's flat
// SeriesPoint[] into the SeriesByKey shape chartConfigs builders expect,
// instantiates a Chart.js chart in a <canvas>, and cleans up on unmount.
//
// Boundary contract:
// - Chart.js leaks GPU resources if you don't .destroy() — handled here.
// - responsive: true on the chart config + a relative-positioned wrapper
//   gives ResizeObserver-driven resizing for free (Chart.js built-in).
// - Re-renders the chart from scratch when section.series, configKey,
//   or section.notes change. Cheap because data volume is small.

import { useEffect, useRef } from "react";
import {
  Chart,
  type ChartConfiguration,
  // Controllers + elements actually used by the 5 chart configs:
  LineController,
  BarController,
  LineElement,
  BarElement,
  PointElement,
  // Scales:
  LinearScale,
  TimeScale,
  // Plugins:
  Filler,
  Legend,
  Tooltip,
} from "chart.js";
import "chartjs-adapter-date-fns";

import type { Section, SeriesPoint } from "@/types/brief";
import {
  chartConfigs,
  type ChartConfigKey,
  type SeriesByKey,
} from "@/lib/chartConfigs";

// Selective registration trims ~25KB gzipped vs registerables.
// Chart.register is idempotent so this is safe across HMR + re-mounts.
Chart.register(
  LineController,
  BarController,
  LineElement,
  BarElement,
  PointElement,
  LinearScale,
  TimeScale,
  Filler,
  Legend,
  Tooltip,
);

interface BriefChartProps {
  section: Section;
  configKey: ChartConfigKey;
  height?: number;
}

// Group SeriesPoint[] (where each point has a `key`) into the
// SeriesByKey shape: Record<key, [ts, value][]>. Points without a key
// fall under the empty-string bucket (defensive; Section.tsx should
// always populate `key`).
function groupSeries(series: SeriesPoint[]): SeriesByKey {
  const out: SeriesByKey = {};
  for (const pt of series) {
    const k = pt.key ?? "";
    if (!out[k]) out[k] = [];
    out[k].push([pt.ts, pt.value]);
  }
  // Sort each bucket chronologically so Chart.js time scales render correctly.
  for (const k of Object.keys(out)) {
    out[k].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  }
  return out;
}

export function BriefChart({ section, configKey, height = 280 }: BriefChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const builder = chartConfigs[configKey];
    if (!builder) return;

    const grouped = groupSeries(section.series);
    const config = builder({
      series: grouped,
      notes: section.notes,
    });

    // Chart.js expects a non-generic Chart constructor; cast the union here.
    chartRef.current = new Chart(canvas, config as ChartConfiguration);

    return () => {
      // Tear down GPU + DOM resources before the next mount.
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [section.series, section.notes, configKey]);

  return (
    <div
      style={{
        height: `${height}px`,
        position: "relative",
        width: "100%",
      }}
      role="img"
      aria-label={`${section.title} chart`}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
