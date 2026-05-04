import type { Brief, Section } from "@/types/brief";
import { Mark } from "./Mark";
import { splitBigNum, formatNewsMeta } from "@/lib/format";

interface CoverProps {
  brief?: Brief;
  sections: Section[];
}

export function Cover({ brief, sections }: CoverProps) {
  const cover = brief?.cover_metric;
  const headlines = (sections.find((s) => s.slug === "headlines")?.news || []).slice(0, 4);

  return (
    <div className="tb-cover" id="cover">
      <div>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          Today&rsquo;s Number
        </div>
        {cover && (
          <>
            <div className="bignum" aria-label={`${cover.label}: ${cover.value}`}>
              {splitBigNum(cover.value)}
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
          </>
        )}
      </div>

      <div style={{ borderLeft: "1px solid var(--rule)", paddingLeft: 28 }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>
          In this issue
        </div>
        <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 12 }}>
          {headlines.map((h, i) => (
            <li
              key={i}
              className={h.changed ? "tb-cover-line is-changed" : "tb-cover-line"}
              style={{
                display: "grid",
                gridTemplateColumns: "20px 1fr",
                gap: 10,
                alignItems: "baseline",
              }}
            >
              <Mark kind={h.tone || "neu"} />
              <div>
                <div style={{ fontSize: 13.5, lineHeight: 1.45, textWrap: "pretty" }}>
                  {h.headline}
                </div>
                <div className="tb-news-meta" style={{ marginTop: 4 }}>
                  {formatNewsMeta(h)}
                  {h.changed ? " · NEW" : ""}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
