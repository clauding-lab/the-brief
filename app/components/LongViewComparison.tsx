import type { ComparisonBlock } from "@/types/brief";

interface LongViewComparisonProps {
  block: ComparisonBlock;
}

// Auto-pick column count: 2 default, 3 when the row count crosses the
// threshold where vertical scroll becomes the bigger cost than internal
// card cramping. Tuned at >= 7 from the visual mockup tradeoff.
const THREE_COLUMN_THRESHOLD = 7;

export function LongViewComparison({ block }: LongViewComparisonProps) {
  const useThreeColumns = block.rows.length >= THREE_COLUMN_THRESHOLD;
  const gridClass = useThreeColumns
    ? "tb-longview-cmp-grid-3"
    : "tb-longview-cmp-grid-2";

  return (
    <div className="tb-longview-cmp">
      <div className="tb-longview-cmp-header">
        {block.before_label} &nbsp;→&nbsp; {block.after_label}
      </div>
      <div className="tb-longview-cmp-rule" />
      <div className={gridClass}>
        {block.rows.map((row, i) => {
          const afterToneClass = row.tone
            ? `tb-longview-cmp-val-${row.tone}`
            : "";
          return (
            <div key={i} className="tb-longview-cmp-row">
              <div className="tb-longview-cmp-row-title">{row.title}</div>
              <div className="tb-longview-cmp-vals">
                <div>
                  <div className="tb-longview-cmp-lab">{block.before_label}</div>
                  <div className="tb-longview-cmp-val">{row.before}</div>
                </div>
                <div>
                  <div className="tb-longview-cmp-lab">{block.after_label}</div>
                  <div className={`tb-longview-cmp-val ${afterToneClass}`.trim()}>
                    {row.after}
                  </div>
                </div>
              </div>
              <p className="tb-longview-cmp-desc">{row.description}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
