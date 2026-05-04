interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  stroke?: number;
}

export function Sparkline({
  data,
  width = 80,
  height = 22,
  color = "var(--ink)",
  stroke = 1,
}: SparklineProps) {
  if (!data || data.length === 0) return null;
  const pad = 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = data
    .map((v, i) => {
      const x = pad + (i / Math.max(data.length - 1, 1)) * (width - pad * 2);
      const y = pad + (1 - (v - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const lastX = pad + (width - pad * 2);
  const lastY = pad + (1 - (data[data.length - 1] - min) / span) * (height - pad * 2);
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={stroke} />
      <circle cx={lastX} cy={lastY} r={2} fill={color} />
    </svg>
  );
}
