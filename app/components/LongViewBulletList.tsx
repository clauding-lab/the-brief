import type { ReactNode } from "react";
import type { BulletListBlock } from "@/types/brief";

interface LongViewBulletListProps {
  block: BulletListBlock;
}

// Markdown-light: split text on **...** segments and render <strong> for each.
// No other markdown features (no italic, no links, no nested lists).
// Regex is anchored to a non-greedy match between paired **...**.
function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    const match = part.match(/^\*\*([^*]+)\*\*$/);
    if (match) {
      return <strong key={i}>{match[1]}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

export function LongViewBulletList({ block }: LongViewBulletListProps) {
  return (
    <div className="tb-longview-bullets">
      {block.eyebrow && (
        <>
          <div className="tb-longview-bullets-eyebrow">{block.eyebrow}</div>
          <div className="tb-longview-bullets-rule" />
        </>
      )}
      <ul>
        {block.items.map((item, i) => {
          const toneClass = item.tone
            ? `tb-longview-bullets-tone-${item.tone}`
            : "";
          return (
            <li key={i} className={toneClass}>
              <span className="tb-longview-bullets-mark">▸</span>
              <span>{renderInline(item.text)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
