import type { Tone } from "@/types/brief";
import { Sparkline } from "./Sparkline";

interface StatStackProps {
  label: string;
  value: string;
  sub?: string;
  tone?: Tone;
  spark?: number[];
  sparkColor?: string;
  delta?: string;
  deltaPct?: string;
  changed?: boolean;
}

export function StatStack({
  label,
  value,
  sub,
  spark,
  sparkColor,
  delta,
  deltaPct,
  changed,
}: StatStackProps) {
  const deltaTone = !delta
    ? "neu"
    : delta.startsWith("−") || delta.startsWith("-")
      ? "bear"
      : delta.startsWith("+")
        ? "bull"
        : "neu";

  return (
    <div
      className={`tb-statstack${changed ? " is-changed" : ""}`}
      style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}
    >
      <div
        className="eyebrow"
        style={{ fontSize: 9, display: "flex", alignItems: "center", gap: 6 }}
      >
        <span>{label}</span>
        {changed && <span className="tb-changed-dot" title="Changed since yesterday" />}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 8,
          justifyContent: "space-between",
        }}
      >
        <div
          className="bignum"
          // 18px = the §6 snapshot-value step (was 26 pre-facelift).
          style={{ fontSize: 18, fontWeight: 300, letterSpacing: "-0.02em" }}
        >
          {value}
        </div>
        {spark && spark.length > 0 && (
          <Sparkline data={spark} width={56} height={18} color={sparkColor || "var(--ink-3)"} />
        )}
      </div>
      {(delta || deltaPct) && (
        <div className={`tb-delta tb-delta-${deltaTone}`}>
          {delta && <span className="tb-delta-abs">{delta}</span>}
          {deltaPct && <span className="tb-delta-pct">{deltaPct}</span>}
        </div>
      )}
      {sub && !delta && <div style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{sub}</div>}
      {sub && delta && (
        <div style={{ fontSize: 10, color: "var(--ink-4)", letterSpacing: "0.02em" }}>{sub}</div>
      )}
    </div>
  );
}
