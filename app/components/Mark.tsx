import type { Tone } from "@/types/brief";

interface MarkProps {
  kind?: Tone;
}

export function Mark({ kind = "neu" }: MarkProps) {
  const ch = kind === "bull" ? "▲" : kind === "bear" ? "▼" : kind === "warn" ? "◆" : "◦";
  return <span className={`mark mark-${kind}`}>{ch}</span>;
}
