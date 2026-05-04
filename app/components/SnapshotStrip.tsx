import type { Section } from "@/types/brief";
import { Hair } from "./Hair";
import { StatStack } from "./StatStack";

interface SnapshotStripProps {
  section?: Section;
}

export function SnapshotStrip({ section }: SnapshotStripProps) {
  if (!section) return null;
  const items = (section.metrics || []).filter((m) => m.is_snapshot);
  if (items.length === 0) return null;

  return (
    <div className="tb-snapshot" id="snapshot">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div className="eyebrow">§01 — Market Snapshot</div>
        <div
          style={{
            fontSize: 10.5,
            color: "var(--ink-3)",
            letterSpacing: "0.12em",
          }}
        >
          {section.verdict ? section.verdict.toUpperCase() : ""}
        </div>
      </div>
      <Hair style={{ marginTop: 14 }} />
      <div className="tb-snapshot-row">
        {items.map((it, i) => (
          <div key={i} className="tb-snapshot-cell">
            <StatStack
              label={it.label}
              value={it.value}
              sub={it.sub}
              tone={it.tone}
              spark={it.spark}
              delta={it.delta}
              deltaPct={it.delta_pct}
              changed={it.changed}
              sparkColor={`var(--${
                it.tone === "bull"
                  ? "bull"
                  : it.tone === "bear"
                    ? "bear"
                    : it.tone === "warn"
                      ? "warn"
                      : "ink-3"
              })`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
