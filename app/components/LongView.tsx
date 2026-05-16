"use client";

import { useEffect, useState } from "react";
import type { LongViewData } from "@/types/brief";
import { Hair } from "./Hair";
import { formatLongViewEyebrow } from "@/lib/format";

interface LongViewProps {
  data: LongViewData | null;
}

// Compare today vs posted_at, both interpreted in Asia/Dhaka, returning true
// when today's calendar date is STRICTLY after the posted calendar date.
// Uses en-CA locale because it formats as YYYY-MM-DD which sorts lexically.
function isPostedBeforeToday(postedAt: string): boolean {
  const posted = new Date(postedAt);
  if (isNaN(posted.getTime())) return false;
  const opts: Intl.DateTimeFormatOptions = { timeZone: "Asia/Dhaka" };
  const todayBDT = new Date().toLocaleDateString("en-CA", opts);
  const postedBDT = posted.toLocaleDateString("en-CA", opts);
  return todayBDT > postedBDT;
}

export function LongView({ data }: LongViewProps) {
  // Track whether the section should render with the diff-stale treatment.
  // True iff: body has the .tb-diff class AND today (BDT) > posted_at (BDT).
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!data) return;

    const recompute = () => {
      const diffOn = document.body.classList.contains("tb-diff");
      setStale(diffOn && isPostedBeforeToday(data.posted_at));
    };

    recompute();

    // Watch for diff-mode toggle (ClientApp toggles body.tb-diff via classList).
    const obs = new MutationObserver(recompute);
    obs.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, [data]);

  if (!data) return null;

  return (
    <section
      id="longview"
      className={`tb-longview${stale ? " tb-diff-stale" : ""}`}
      aria-labelledby="longview-title"
    >
      <div className="tb-longview-eyebrow">{formatLongViewEyebrow(data.posted_at)}</div>
      <Hair style={{ marginTop: 12, marginBottom: 20 }} />

      <h2 id="longview-title" className="tb-longview-title">
        {data.title}
      </h2>

      <p className="tb-longview-lead">{data.lead}</p>

      {data.chart_spec && (
        <div className="tb-longview-chart-placeholder" role="note">
          <em>Chart rendering for The Long View ships in v1.1.1. The data below
          and in the body paragraphs reflects the source.</em>
        </div>
      )}

      <div className="tb-longview-body">
        {data.body_paragraphs.map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>

      <Hair style={{ marginTop: 28, marginBottom: 16 }} />
      <div className="tb-longview-takeaway">
        <div className="tb-longview-takeaway-label">BANKER READ</div>
        <p>{data.banker_read}</p>
      </div>
    </section>
  );
}
