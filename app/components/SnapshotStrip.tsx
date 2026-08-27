import type { Metric, Section } from "@/types/brief";
import { Hair } from "./Hair";
import { StatStack } from "./StatStack";
import { cleanMetricValue } from "@/lib/format";

interface SnapshotStripProps {
  sections: Section[];
}

// Fallback cell map (spec §7.2, owner veto §11.4): no payload emits a
// `snapshot` SECTION at all today (slugs on real issues: headlines, bb,
// banking, fx, dse, tbond, fiscal, macro, iran, remit[, comm]) — the old
// `section?` prop meant the strip NEVER rendered on real data and the
// scroll-spy's "snapshot" target didn't exist. When no snapshot section is
// present, six canonical cells derive by case-insensitive substring label
// lookup against the measured real labels below. Order = display order.
const FALLBACK_CELLS: ReadonlyArray<{ label: string; slugs: readonly string[] }> = [
  { label: "usd/bdt mid", slugs: ["fx"] },
  { label: "dsex", slugs: ["dse"] },
  { label: "91d t-bill cut-off", slugs: ["tbond"] },
  { label: "brent", slugs: ["iran"] },
  { label: "gold", slugs: ["fx", "comm"] }, // fx on real issues; comm fallback
  { label: "monthly remittance", slugs: ["remit"] },
];

function deriveFallbackItems(sections: Section[]): Metric[] {
  const bySlug = new Map(sections.map((s) => [s.slug, s]));
  const items: Metric[] = [];
  for (const cell of FALLBACK_CELLS) {
    for (const slug of cell.slugs) {
      const metric = bySlug
        .get(slug)
        ?.metrics?.find((m) => m.label.toLowerCase().includes(cell.label));
      if (metric) {
        items.push(metric);
        break;
      }
    }
  }
  return items;
}

export function SnapshotStrip({ sections }: SnapshotStripProps) {
  // A real snapshot-slug section with is_snapshot metrics wins (current
  // behavior, kept); otherwise derive the six canonical cells.
  const snapshotSection = sections.find((s) => s.slug === "snapshot");
  const own = (snapshotSection?.metrics || []).filter((m) => m.is_snapshot);
  const items = own.length > 0 ? own : deriveFallbackItems(sections);
  if (items.length === 0) return null;

  return (
    <div className="tb-snapshot" id="snapshot">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div className="eyebrow">
          {own.length > 0 ? "§01 — Market Snapshot" : "Market snapshot"}
        </div>
        {/* Verdict line only exists when a real snapshot section supplied the cells. */}
        {own.length > 0 && snapshotSection?.verdict && (
          <div
            style={{
              fontSize: 10.5,
              color: "var(--ink-3)",
              letterSpacing: "0.12em",
            }}
          >
            {snapshotSection.verdict.toUpperCase()}
          </div>
        )}
      </div>
      <Hair style={{ marginTop: 14 }} />
      <div className="tb-snapshot-row">
        {items.map((it, i) => (
          <div key={i} className="tb-snapshot-cell">
            <StatStack
              label={it.label}
              value={cleanMetricValue(it.value)}
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
