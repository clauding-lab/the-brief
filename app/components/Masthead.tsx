"use client";

import { useLayoutEffect, useState } from "react";
import type { Brief, DataSource } from "@/types/brief";
import { Hair } from "./Hair";
import { formatBriefDate, formatPublishedAt } from "@/lib/format";
import { MastheadLensPill } from "./MastheadLensPill";
import { useReducedMotion } from "@/lib/useReducedMotion";

const LIVE_WINDOW_MS = 10 * 60 * 1000; // "Live" claim expires 10 min after fetch
const LIVE_RECHECK_MS = 60 * 1000; // re-evaluate the 10-min window every 60s while the tab stays open

interface MastheadProps {
  brief?: Brief;
  source?: DataSource;
  /** Epoch ms of the last data fetch; formatted to Asia/Dhaka for the Live stamp. */
  fetchedAt?: number;
  /** Total body sections in this issue — drives "{n} sections" (was hardcoded 15). */
  sectionCount?: number;
  /** A fixed past issue (/issue/[no]) — swaps the "Static" source label for
   * an honest "Archived issue" one, since `_source` defaults to "static"
   * for permalinks too and that reads as a broken offline fallback rather
   * than what it actually is. */
  historical?: boolean;
}

function isFreshNow(fetchedAt: number | undefined): boolean {
  return fetchedAt != null && Date.now() - fetchedAt < LIVE_WINDOW_MS;
}

export function Masthead({ brief, source, fetchedAt, sectionCount, historical }: MastheadProps) {
  const dateLabel = formatBriefDate(brief?.brief_date);
  const issueNo = brief?.issue_no ?? 87;
  const vol = brief?.volume ?? 1;
  const readMin = brief?.read_minutes ?? 15;
  const sourceLabel = historical
    ? "Archived issue"
    : source === "live"
      ? "Live"
      : source === "cache"
        ? "Cached"
        : "Static";
  const reducedMotion = useReducedMotion();
  // Real fetch time in BDT (Asia/Dhaka), mirroring StatusBar — replaces the old
  // hardcoded "14:02 BST". Drops to just the source label when no fetch time exists
  // (e.g. the static fallback), so we never show a fabricated clock.
  const fetchedTime = fetchedAt
    ? new Date(fetchedAt).toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Dhaka",
      })
    : null;
  // The clock above is page-LOAD time, not the issue's publish time — the two
  // used to be conflated under one "Live · HH:MM" label. "Live" now only
  // claims to be current while the fetch itself is fresh; past that it just
  // states when the page fetched, and the real publish time (from the
  // payload, not the client clock) prints separately below.
  //
  // `Date.now()` is an impure read, so it can't run inline during render
  // (React's purity rule) — computed in an effect instead, same pattern as
  // ClientApp's post-mount localStorage reads. useLayoutEffect (not
  // useEffect) so the correct value is set BEFORE the browser paints the
  // first frame — review round 1, MED-2 flagged a visible "not live" → "live"
  // pop-in a tick after load with the plain-effect version. Re-checked every
  // 60s so "Live" correctly drops off after 10 minutes even if the tab is
  // left open with no re-render to trigger it otherwise.
  const [isFreshFetch, setIsFreshFetch] = useState(false);
  useLayoutEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- deliberate post-mount impure read (Date.now()); see comment above
    setIsFreshFetch(isFreshNow(fetchedAt));
    const id = setInterval(() => setIsFreshFetch(isFreshNow(fetchedAt)), LIVE_RECHECK_MS);
    return () => clearInterval(id);
  }, [fetchedAt]);
  const publishedLabel = formatPublishedAt(brief?.published_at);

  return (
    <header className="tb-masthead-full" id="masthead">
      <div className="tb-masthead-meta">
        <div>
          No. {String(issueNo).padStart(2, "0")} / Vol. {String(vol).padStart(2, "0")}
        </div>
        <div className="tb-masthead-date-row">
          <span>{dateLabel}</span>
          <MastheadLensPill lens={brief?.lens} frame={brief?.frame} briefDate={brief?.brief_date} />
        </div>
        <div>
          <div className="tb-live">
            {isFreshFetch && <span className="pulse" />}
            <span>
              {isFreshFetch ? "Live · " : ""}
              {fetchedTime ? `Fetched ${fetchedTime} BDT` : sourceLabel}
            </span>
          </div>
          {publishedLabel && <div className="tb-published">Published {publishedLabel}</div>}
        </div>
      </div>

      <Hair style={{ marginTop: 14 }} />

      <div className="tb-masthead-hero">
        <h1 className="tb-wordmark-big">
          The Brief<span className="dot">.</span>
        </h1>
        <div className="tb-tagline">
          Daily macro &amp; markets read for Bangladesh banking professionals. One brief.
          Numbers, news, and a banker&rsquo;s read on what matters.
        </div>
      </div>

      {brief?.todays_call && (
        <div className="tb-todays-call">
          <span className="label">Today&rsquo;s Call</span>
          <div>
            <div className="body">{brief.todays_call}</div>
            <div className="byline">— Desk Editor · The Brief</div>
          </div>
        </div>
      )}

      <Hair />

      <div className="tb-masthead-foot">
        <div className="tb-tag-row">
          <span className="tag">Macro</span>
          <span className="tag">Markets</span>
          <span className="tag">Banking</span>
          <span className="tag tag-soft">{sectionCount ?? 15} sections</span>
        </div>
        <div className="tb-masthead-actions">
          <span className="tb-readtime">Read time · {readMin} min</span>
          <a
            href="#subscribe"
            className="tb-btn-cta"
            onClick={(e) => {
              e.preventDefault();
              const el = document.getElementById("subscribe");
              if (el) el.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" });
            }}
          >
            Subscribe →
          </a>
        </div>
      </div>
    </header>
  );
}
