import type { ReactNode } from "react";
import type { NewsItem } from "@/types/brief";

export function formatBriefDate(s?: string): string {
  if (!s) return "Mon · 04 May 2026";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  // Force Asia/Dhaka on both server (UTC) and client (BDT) so the date can't
  // differ across the hydration boundary for near-midnight-UTC timestamps
  // (React #418). Same policy as formatNewsMeta/formatLongViewEyebrow (da8c968).
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "Asia/Dhaka",
    })
      .formatToParts(d)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.weekday} · ${parts.day} ${parts.month} ${parts.year}`;
}

/** "01 Mar 2026" — the as-of date on a metric that is older than its cadence.
 *
 * Forced to Asia/Dhaka like every other date formatter here, so the server (UTC)
 * and the client (BDT) can't disagree across the hydration boundary. `held_from`
 * arrives as a bare ISO date, which `new Date()` reads as UTC midnight — in any
 * timezone behind UTC that would render as the previous day. */
export function formatVintageDate(s?: string | null): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Dhaka",
  });
}

/** "09:14 BDT · 22 Aug 2026" — the issue's real publish timestamp (from the
 * payload's `published_at`, UTC ISO 8601), NOT the client's page-load clock.
 * The masthead used to print only a "LIVE · HH:MM BDT" stamp that was in
 * fact the moment the browser fetched the page — the issue's actual publish
 * time appeared nowhere. Returns null so callers can omit the line cleanly
 * when the field is absent (e.g. the static fallback). */
export function formatPublishedAt(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const time = d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Dhaka",
  });
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "Asia/Dhaka",
    })
      .formatToParts(d)
      .map((p) => [p.type, p.value])
  );
  return `${time} BDT · ${parts.day} ${parts.month} ${parts.year}`;
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
