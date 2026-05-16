import type { ProseBlock } from "@/types/brief";

interface LongViewProseProps {
  block: ProseBlock;
}

export function LongViewProse({ block }: LongViewProseProps) {
  return (
    <div className="tb-longview-prose">
      {block.paragraphs.map((paragraph, i) => (
        <p key={i}>{paragraph}</p>
      ))}
    </div>
  );
}
