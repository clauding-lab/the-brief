import type { CSSProperties } from "react";

interface HairProps {
  tone?: "rule" | "soft" | "faint";
  style?: CSSProperties;
}

export function Hair({ tone = "rule", style }: HairProps) {
  const cls = tone === "soft" ? "hair-soft" : tone === "faint" ? "hair-faint" : "hair";
  return <div className={cls} style={style} />;
}
