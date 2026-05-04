import type { ReactNode } from "react";
import type { NewsItem } from "@/types/brief";

export function formatBriefDate(s?: string): string {
  if (!s) return "Mon · 04 May 2026";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${days[d.getDay()]} · ${String(d.getDate()).padStart(2, "0")} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

export function formatNewsMeta(n: NewsItem): string {
  const parts: string[] = [];
  if (n.published_at) {
    const d = new Date(n.published_at);
    if (!isNaN(d.getTime())) {
      parts.push(d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }));
    }
  }
  if (n.source) parts.push(n.source);
  return parts.join(" · ");
}

export function splitBigNum(value: string | number | undefined): ReactNode {
  if (typeof value !== "string") return value ?? null;
  const m = value.match(/^([^.]*)(\.)(.*)$/);
  if (!m) return value;
  return (
    <>
      {m[1]}
      <span className="dot">{m[2]}</span>
      {m[3]}
    </>
  );
}
