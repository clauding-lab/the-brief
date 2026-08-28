"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { BarChartBlock } from "@/types/brief";

interface LongViewBarChartProps {
  block: BarChartBlock;
}

// Fixed pixel geometry. The SVG's viewBox is built as
// `0 0 <measured container width> <chartHeight>`, so one viewBox unit is one
// CSS pixel and everything below renders at exactly the size named here.
// Only the bar track stretches with the container — type never scales: the
// 11px label/value and 9.5px ref-text sizes come from the CSS classes in
// globals.css and land at their nominal px at every viewport width.
const ROW_HEIGHT = 22;
const ROW_GAP = 8;
const LABEL_COLUMN = 110;
const VALUE_COLUMN = 70;
const LABEL_GAP = 8;
const VALUE_GAP = 6;
const BAR_AREA_X = LABEL_COLUMN + LABEL_GAP;
// 8% headroom past the largest bar so the longest one doesn't touch the
// value column.
const SCALE_HEADROOM = 1.08;

export function LongViewBarChart({ block }: LongViewBarChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number | null>(null);

  // Measure the container synchronously before first paint (useLayoutEffect),
  // then track resizes. The SVG keeps an explicit CSS height equal to
  // chartHeight (known without measuring — row geometry is fixed px), so the
  // pre-measurement empty frame occupies its final box and there is no
  // layout jump when the rows appear.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () =>
      setWidth(Math.round(el.getBoundingClientRect().width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const maxValue = Math.max(
    ...block.items.map((i) => i.value),
    block.reference?.value ?? 0
  );
  const scaleMax = maxValue * SCALE_HEADROOM;

  const rowOuterHeight = ROW_HEIGHT + ROW_GAP;
  const chartHeight = block.items.length * rowOuterHeight + ROW_GAP;
  const REF_LABEL_Y = chartHeight - 4;

  // A 0-width container (display:none ancestor, e.g. a print-hidden branch)
  // must not produce negative bar tracks or NaN positions — skip the rows
  // until a real width exists.
  const isMeasured = width !== null && width > 0;
  const viewBoxWidth = isMeasured ? width : 0;
  const barAreaWidth = Math.max(
    0,
    viewBoxWidth - BAR_AREA_X - VALUE_COLUMN - VALUE_GAP
  );
  const fractionOfScale = (value: number) =>
    scaleMax > 0 ? value / scaleMax : 0;

  const refX =
    isMeasured && block.reference !== undefined
      ? BAR_AREA_X + fractionOfScale(block.reference.value) * barAreaWidth
      : null;

  return (
    <div className="tb-longview-bar" ref={containerRef}>
      {block.eyebrow && (
        <>
          <div className="tb-longview-bar-eyebrow">{block.eyebrow}</div>
          <div className="tb-longview-bar-rule" />
        </>
      )}
      <svg
        className="tb-longview-bar-svg"
        style={{ height: chartHeight }}
        viewBox={`0 0 ${viewBoxWidth} ${chartHeight}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={block.eyebrow ?? "Bar chart"}
      >
        {isMeasured &&
          block.items.map((item, i) => {
            const cy = ROW_GAP + i * rowOuterHeight + ROW_HEIGHT / 2;
            const barWidth = Math.max(
              1,
              fractionOfScale(item.value) * barAreaWidth
            );
            const fillClass = item.tone
              ? `tb-longview-bar-fill-${item.tone}`
              : "tb-longview-bar-fill-default";
            const display = item.display ?? item.value.toLocaleString("en-GB");
            return (
              <g key={i}>
                <text
                  className="tb-longview-bar-label"
                  x={LABEL_COLUMN}
                  y={cy}
                  textAnchor="end"
                  dominantBaseline="middle"
                >
                  {item.label}
                </text>
                <rect
                  className={fillClass}
                  x={BAR_AREA_X}
                  y={cy - ROW_HEIGHT / 2}
                  width={barWidth}
                  height={ROW_HEIGHT}
                  rx={2}
                />
                <text
                  className="tb-longview-bar-value"
                  x={BAR_AREA_X + barWidth + VALUE_GAP}
                  y={cy}
                  textAnchor="start"
                  dominantBaseline="middle"
                >
                  {display}
                </text>
              </g>
            );
          })}
        {refX !== null && block.reference && (
          <g>
            <line
              className="tb-longview-bar-ref-line"
              x1={refX}
              x2={refX}
              y1={0}
              y2={chartHeight}
            />
            <text
              className="tb-longview-bar-ref-text"
              x={refX + 6}
              y={REF_LABEL_Y}
              textAnchor="start"
              dominantBaseline="alphabetic"
            >
              {block.reference.label}
            </text>
          </g>
        )}
      </svg>
      {block.unit && (
        <div className="tb-longview-bar-unit">All values in {block.unit}.</div>
      )}
    </div>
  );
}
