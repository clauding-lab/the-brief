"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { BarChartBlock } from "@/types/brief";

interface LongViewBarChartProps {
  block: BarChartBlock;
}

// Pixel geometry. The SVG's viewBox is built as
// `0 0 <measured container width> <chartHeight>`, so one viewBox unit is one
// CSS pixel and everything below renders at exactly the size named here.
// Only the bar track stretches with the container — type never scales: the
// 11px label/value and 9.5px ref-text sizes come from the CSS classes in
// globals.css and land at their nominal px at every viewport width.
const ROW_HEIGHT = 22;
const ROW_GAP = 8;
const LABEL_GAP = 8;
const VALUE_GAP = 6;
// 8% headroom past the largest bar so the longest one doesn't touch the
// value column.
const SCALE_HEADROOM = 1.08;

// The label and value columns are responsive: fixed 110/70 chrome at wide
// containers, shrinking as a fraction of the container so the bar track
// keeps carrying the comparison at phone widths (at a fixed 194px chrome the
// track fell to 13% of a 320px-viewport container). The label column floors
// at 72px — enough for the longest live division name ("Chattogram", 10
// chars of 11px mono ≈ 66px); a longer label compresses via SVG textLength
// rather than silently clipping at the SVG edge.
const LABEL_COLUMN_MAX = 110;
const LABEL_COLUMN_MIN = 72;
const LABEL_COLUMN_FRACTION = 0.26;
const VALUE_COLUMN_MAX = 70;
const VALUE_COLUMN_MIN = 34;
const VALUE_COLUMN_FRACTION = 0.16;

// Deliberate overestimates of glyph advance (JetBrains Mono's true advance
// is 0.60em) so collision/overflow checks err toward acting, never toward
// missing a real overlap. The ref text adds its 0.08em letter-spacing.
const MONO_CHAR_FACTOR = 0.62;
const REF_CHAR_FACTOR = 0.7;
const LABEL_FONT_PX = 11;
const VALUE_FONT_PX = 11;
const REF_FONT_PX = 9.5;
// A value label whose box comes within this many px of the ref line counts
// as a collision; a shifted label clears the line by REF_LINE_CLEARANCE.
const COLLISION_PAD = 3;
const REF_LINE_CLEARANCE = 5;

// The server (and a client whose bundle never runs) renders the chart at
// this width; `.tb-longview-bar-svg { width: 100% }` + preserveAspectRatio
// scale that 600-unit drawing proportionally into whatever box CSS gives
// it, so no-JS readers still get real bars. The first client render uses
// the same seed, so server and client markup agree (no hydration mismatch);
// the layout effect below corrects to the true width before first paint.
const SSR_FALLBACK_WIDTH = 600;

export function LongViewBarChart({ block }: LongViewBarChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState<number>(SSR_FALLBACK_WIDTH);

  // Measure the container synchronously before first paint (useLayoutEffect),
  // then track resizes. Math.floor (not round) keeps the 1:1 claim honest:
  // a floored viewBox width is never wider than the CSS box, so with
  // preserveAspectRatio="meet" the height ratio (exactly 1) is the limiting
  // one and content renders at scale 1.0 — rounding up would shrink
  // everything sub-pixel. A 0-width measurement (display:none ancestor,
  // e.g. a print-hidden branch) is skipped so real state is never
  // overwritten with a degenerate width.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const measured = Math.floor(el.getBoundingClientRect().width);
      if (measured > 0) setWidth(measured);
    };
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

  const labelColumn = Math.max(
    LABEL_COLUMN_MIN,
    Math.min(LABEL_COLUMN_MAX, Math.round(width * LABEL_COLUMN_FRACTION))
  );
  const valueColumn = Math.max(
    VALUE_COLUMN_MIN,
    Math.min(VALUE_COLUMN_MAX, Math.round(width * VALUE_COLUMN_FRACTION))
  );
  const barAreaX = labelColumn + LABEL_GAP;
  const barAreaWidth = Math.max(0, width - barAreaX - valueColumn - VALUE_GAP);
  const fractionOfScale = (value: number) =>
    scaleMax > 0 ? value / scaleMax : 0;

  const refX =
    block.reference !== undefined
      ? barAreaX + fractionOfScale(block.reference.value) * barAreaWidth
      : null;

  // Right-anchor the ref label whenever the default left-anchored placement
  // would run past the SVG's right edge (SVG clips overflow silently).
  const refLabelWidth = block.reference
    ? block.reference.label.length * REF_FONT_PX * REF_CHAR_FACTOR
    : 0;
  const refLabelOverflowsRight =
    refX !== null && refX + VALUE_GAP + refLabelWidth > width;

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
        viewBox={`0 0 ${width} ${chartHeight}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={block.eyebrow ?? "Bar chart"}
      >
        {block.items.map((item, i) => {
          const cy = ROW_GAP + i * rowOuterHeight + ROW_HEIGHT / 2;
          const barWidth = Math.max(
            1,
            fractionOfScale(item.value) * barAreaWidth
          );
          const fillClass = item.tone
            ? `tb-longview-bar-fill-${item.tone}`
            : "tb-longview-bar-fill-default";
          const display = item.display ?? item.value.toLocaleString("en-GB");

          // Compress an over-long division label into the label column via
          // textLength instead of letting the SVG edge clip its start.
          const labelWidthEstimate =
            item.label.length * LABEL_FONT_PX * MONO_CHAR_FACTOR;
          const labelFitProps =
            labelWidthEstimate > labelColumn
              ? {
                  textLength: labelColumn,
                  lengthAdjust: "spacingAndGlyphs" as const,
                }
              : {};

          // Collision-proof the ref line deterministically: if this row's
          // value label box (padded) would sit under the line, place the
          // label just to the RIGHT of the line instead — the benchmark
          // stays drawn full-height and no label is struck through. The
          // shifted label always fits: the reference sits below the longest
          // bar, whose own label fits by construction.
          const naturalValueX = barAreaX + barWidth + VALUE_GAP;
          const valueWidthEstimate =
            display.length * VALUE_FONT_PX * MONO_CHAR_FACTOR;
          const collidesWithRefLine =
            refX !== null &&
            refX >= naturalValueX - COLLISION_PAD &&
            refX <= naturalValueX + valueWidthEstimate + COLLISION_PAD;
          const valueX =
            collidesWithRefLine && refX !== null
              ? refX + REF_LINE_CLEARANCE
              : naturalValueX;

          return (
            <g key={i}>
              <text
                className="tb-longview-bar-label"
                x={labelColumn}
                y={cy}
                textAnchor="end"
                dominantBaseline="middle"
                {...labelFitProps}
              >
                {item.label}
              </text>
              <rect
                className={fillClass}
                x={barAreaX}
                y={cy - ROW_HEIGHT / 2}
                width={barWidth}
                height={ROW_HEIGHT}
                rx={2}
              />
              <text
                className="tb-longview-bar-value"
                x={valueX}
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
              x={refLabelOverflowsRight ? refX - VALUE_GAP : refX + VALUE_GAP}
              y={REF_LABEL_Y}
              textAnchor={refLabelOverflowsRight ? "end" : "start"}
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
