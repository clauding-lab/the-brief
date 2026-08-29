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

// A metric value that is a single number carrying 3+ decimal places, with
// only non-digit decoration around it (a leading "$", a trailing "%" / "bn").
// Groups: prefix, integer part (sign + optional thousands commas), fraction,
// suffix. Deliberately whole-string-anchored: a string holding two numbers
// ("3.500-4.000") or a dotted date ("2026.08.29") must NOT match, because
// truncating one number inside a compound string would corrupt it.
const LONG_DECIMAL = /^(\D*?)(-?[\d,]+)\.(\d{3,})(\D*)$/;

// Clean a metric value for display. Two fixes, in order:
//
// 1. Strip repeated `$` chars. The editor LLM sometimes emits "$$108.17"
//    (likely a TeX display-math artefact from training); collapse any run
//    of 2+ to a single `$`.
//
// 2. Cut runaway decimal tails to 2 places. Upstream feeds hand us float32
//    values widened to float64, so BRENT SPOT arrives as "88.01000214" and
//    GOLD as "4512.100098" — that tail is arithmetic noise, not precision,
//    and it was rendering verbatim on the snapshot strip and the KPI tiles.
//
// The cut is a TRUNCATION, not a round: owner decision (2026-08-29) — shown
// "122.9959", he asked for "122.99". Do not "fix" this to Math.round; it
// would print 123.00 there and 8.83 for the 91d T-Bill cut-off's 8.829.
// Truncation is done on the DIGIT STRING, never via Math.trunc(n * 100),
// because the values we are cleaning are precisely the ones carrying float
// error — 8.829 * 100 is 882.9000000000001 in IEEE-754, and a value stored
// as 8.8299999999 would truncate to 8.82 when its true 2dp form is 8.83.
//
// Values already at 2 or fewer decimals are returned untouched, so "9.5"
// stays "9.5" and "185" stays "185" — this pads nothing, it only cuts.
export function cleanMetricValue(v: string | undefined | null): string {
  if (!v) return "";
  const collapsed = v.replace(/\${2,}/g, "$");
  const m = collapsed.match(LONG_DECIMAL);
  if (!m) return collapsed;
  const [, prefix, intPart, frac, suffix] = m;
  const cut = `${prefix}${intPart}.${frac.slice(0, 2)}${suffix}`;
  // Never let the cut collapse a small non-zero value to a bare "0.00" —
  // "0.0004" keeps its full tail rather than being displayed as nothing.
  if (Number(`${intPart.replace(/,/g, "")}.${frac.slice(0, 2)}`) === 0) {
    return collapsed;
  }
  return cut;
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
