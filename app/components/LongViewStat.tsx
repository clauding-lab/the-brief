import type { StatBlock } from "@/types/brief";

interface LongViewStatProps {
  block: StatBlock;
}

export function LongViewStat({ block }: LongViewStatProps) {
  const toneClass = block.tone ? `tb-longview-stat-tone-${block.tone}` : "";
  return (
    <div className="tb-longview-stat">
      <div className={`tb-longview-stat-num ${toneClass}`.trim()}>
        {block.value}
        {block.unit && (
          <span className="tb-longview-stat-unit">{block.unit}</span>
        )}
      </div>
      <div className="tb-longview-stat-meta">
        <div className="tb-longview-stat-label">{block.label}</div>
        <p className="tb-longview-stat-body">{block.body}</p>
      </div>
    </div>
  );
}
