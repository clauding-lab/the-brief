import type { SeriesPoint, SeriesNote } from "@/types/brief";

interface SignatureChartProps {
  series: SeriesPoint[];
  notes?: SeriesNote[];
  yMinPad?: number;
  yMaxPad?: number;
  label?: string;
}

export function SignatureChart({
  series,
  notes = [],
  yMinPad = 1,
  yMaxPad = 1,
  label = "",
}: SignatureChartProps) {
  if (!series || series.length === 0) return null;

  const W = 600;
  const H = 220;
  const pad = { l: 40, r: 12, t: 12, b: 24 };

  const values = series.map((s) => Number(s.value));
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const min = Math.floor(dataMin - yMinPad);
  const max = Math.ceil(dataMax + yMaxPad);
  const span = max - min || 1;

  const x = (i: number) => pad.l + (i / Math.max(series.length - 1, 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / span) * (H - pad.t - pad.b);

  const line = series
    .map((s, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(Number(s.value)).toFixed(1)}`)
    .join(" ");

  // Baseline 0.5px below pad.b so the area fill closes flush against the bottom rule (no seam)
  const baselineY = (H - pad.b + 0.5).toFixed(1);
  const area = `${line} L ${x(series.length - 1).toFixed(1)} ${baselineY} L ${x(0).toFixed(1)} ${baselineY} Z`;

  const yTicks: number[] = [];
  const step = span / 3;
  for (let i = 0; i <= 3; i++) yTicks.push(min + step * i);

  const noteMarkers = (notes || [])
    .map((n) => {
      const idx = series.findIndex((s) => s.ts === n.ts);
      return idx >= 0 ? { ...n, idx } : null;
    })
    .filter((n): n is SeriesNote & { idx: number } => n !== null);

  const monthLabels = series.map((s) => {
    const d = new Date(s.ts);
    return ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"][d.getMonth()];
  });

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: "100%", height: "auto" }}
      role="img"
      aria-label={label}
    >
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--rule-faint)" />
          <text
            x={pad.l - 8}
            y={y(v) + 3}
            textAnchor="end"
            fontSize="10"
            fill="var(--ink-3)"
            fontFamily="var(--mono)"
          >
            {v.toFixed(2)}
          </text>
        </g>
      ))}
      <path d={area} fill="var(--accent-soft)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
      {noteMarkers.map((n, i) => (
        <g key={i}>
          <line
            x1={x(n.idx)}
            x2={x(n.idx)}
            y1={pad.t}
            y2={H - pad.b}
            stroke="var(--ink)"
            strokeDasharray="2 3"
            strokeWidth={1}
          />
          <circle
            cx={x(n.idx)}
            cy={y(Number(series[n.idx].value))}
            r={3}
            fill="var(--ink)"
          />
          <text
            x={x(n.idx) - 6}
            y={pad.t + 14}
            textAnchor="end"
            fontSize="9.5"
            fill="var(--ink)"
            fontFamily="var(--mono)"
            letterSpacing="0.08em"
          >
            {(n.label || "").toUpperCase()}
          </text>
          {n.detail && (
            <text
              x={x(n.idx) - 6}
              y={pad.t + 26}
              textAnchor="end"
              fontSize="9.5"
              fill="var(--ink-3)"
              fontFamily="var(--mono)"
            >
              {n.detail}
            </text>
          )}
        </g>
      ))}
      {monthLabels.map((m, i) => (
        <text
          key={i}
          x={x(i)}
          y={H - 8}
          fontSize="9.5"
          fill="var(--ink-3)"
          textAnchor="middle"
          fontFamily="var(--mono)"
          letterSpacing="0.1em"
        >
          {m}
        </text>
      ))}
    </svg>
  );
}
