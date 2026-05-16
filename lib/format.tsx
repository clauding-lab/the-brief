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
      parts.push(d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", timeZone: "Asia/Dhaka" }));
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

// Strip repeated `$` chars from metric values. The editor LLM sometimes
// emits "$$108.17" (likely a TeX display-math artefact from training);
// collapse any run of 2+ to a single `$`.
export function cleanMetricValue(v: string | undefined | null): string {
  if (!v) return "";
  return v.replace(/\${2,}/g, "$");
}

// Format an ISO timestamp as the Long View eyebrow:
//   EDITOR'S PIN · POSTED MON 12 MAY
// Day-of-week + day + month, all caps, pinned to Asia/Dhaka to avoid the
// SSR (UTC) vs CSR (BDT) day-number mismatch that bit us on news-item dates
// (React #418). See lib/format.tsx::formatNewsMeta for the same pattern.
export function formatLongViewEyebrow(postedAt: string): string {
  const d = new Date(postedAt);
  if (isNaN(d.getTime())) return "EDITOR'S PIN";
  const parts = d
    .toLocaleDateString("en-GB", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      timeZone: "Asia/Dhaka",
    })
    .toUpperCase()
    .split(" ");
  // en-GB returns "MON, 12 MAY" — strip the comma after weekday, keep the rest.
  const weekday = parts[0]?.replace(",", "") ?? "";
  const day = parts[1] ?? "";
  const month = parts[2] ?? "";
  return `EDITOR'S PIN · POSTED ${weekday} ${day} ${month}`;
}
