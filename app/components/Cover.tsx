import type { Brief, Section } from "@/types/brief";
import { Mark } from "./Mark";
import { splitBigNum, cleanMetricValue } from "@/lib/format";

interface CoverProps {
  brief?: Brief;
  sections: Section[];
}

export function Cover({ brief }: CoverProps) {
  const cover = brief?.cover_metric;

  if (!cover) {
    return <div className="tb-cover" id="cover" aria-hidden="true" />;
  }

  return (
    <div className="tb-cover" id="cover">
      <div>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          Today&rsquo;s Number
        </div>
        <div className="bignum" aria-label={`${cover.label}: ${cleanMetricValue(cover.value)}`}>
          {splitBigNum(cleanMetricValue(cover.value))}
        </div>
        <div className="tb-cover-asof">{cover.as_of || "Latest"}</div>
        <div
          style={{
            marginTop: 14,
            fontSize: 12,
            color: "var(--ink-3)",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          {cover.label}
        </div>
        <div style={{ marginTop: 6, fontSize: 13, color: "var(--ink-2)" }}>
          <Mark kind={cover.tone || "neu"} /> {cover.sub}
        </div>
      </div>
    </div>
  );
}
