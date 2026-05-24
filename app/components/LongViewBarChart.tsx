import type { BarChartBlock } from "@/types/brief";

interface LongViewBarChartProps {
  block: BarChartBlock;
}

// SVG viewBox geometry. The component scales to its container via
// preserveAspectRatio, so these are unitless layout numbers.
const VIEWPORT_WIDTH = 600;
const ROW_HEIGHT = 22;
const ROW_GAP = 8;
const LABEL_COLUMN = 110;
const VALUE_COLUMN = 70;
const LABEL_GAP = 8;
const VALUE_GAP = 6;
const BAR_AREA_X = LABEL_COLUMN + LABEL_GAP;
const BAR_AREA_WIDTH = VIEWPORT_WIDTH - BAR_AREA_X - VALUE_COLUMN - VALUE_GAP;
// 8% headroom past the largest bar so the longest one doesn't touch the
// value column.
const SCALE_HEADROOM = 1.08;

export function LongViewBarChart({ block }: LongViewBarChartProps) {
  const maxValue = Math.max(
    ...block.items.map((i) => i.value),
    block.reference?.value ?? 0
  );
  const scaleMax = maxValue * SCALE_HEADROOM;

  const rowOuterHeight = ROW_HEIGHT + ROW_GAP;
  const chartHeight = block.items.length * rowOuterHeight + ROW_GAP;
  const REF_LABEL_Y = chartHeight - 4;

  const refX =
    block.reference !== undefined
      ? BAR_AREA_X + (block.reference.value / scaleMax) * BAR_AREA_WIDTH
      : null;

  return (
    <div className="tb-longview-bar">
      {block.eyebrow && (
        <>
          <div className="tb-longview-bar-eyebrow">{block.eyebrow}</div>
          <div className="tb-longview-bar-rule" />
        </>
      )}
      <svg
        className="tb-longview-bar-svg"
        viewBox={`0 0 ${VIEWPORT_WIDTH} ${chartHeight}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={block.eyebrow ?? "Bar chart"}
      >
        {block.items.map((item, i) => {
          const cy = ROW_GAP + i * rowOuterHeight + ROW_HEIGHT / 2;
          const barWidth = Math.max(
            1,
            (item.value / scaleMax) * BAR_AREA_WIDTH
          );
          const fillClass = item.tone
            ? `tb-longview-bar-fill-${item.tone}`
            : "tb-longview-bar-fill-default";
          const display = item.display ?? item.value.toLocaleString();
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
