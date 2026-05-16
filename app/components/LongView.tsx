"use client";

import { useEffect, useState } from "react";
import type { Block, LongViewData } from "@/types/brief";
import { Hair } from "./Hair";
import { formatLongViewEyebrow } from "@/lib/format";
import { LongViewProse } from "./LongViewProse";
import { LongViewComparison } from "./LongViewComparison";
import { LongViewStat } from "./LongViewStat";
import { LongViewBulletList } from "./LongViewBulletList";

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

// Dispatch a block to its render component by discriminator.
function renderBlock(block: Block, index: number) {
  switch (block.kind) {
    case "prose":
      return <LongViewProse key={index} block={block} />;
    case "comparison":
      return <LongViewComparison key={index} block={block} />;
    case "stat":
      return <LongViewStat key={index} block={block} />;
    case "bullet-list":
      return <LongViewBulletList key={index} block={block} />;
  }
}

export function LongView({ data }: LongViewProps) {
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!data) return;

    const recompute = () => {
      const diffOn = document.body.classList.contains("tb-diff");
      setStale(diffOn && isPostedBeforeToday(data.posted_at));
    };

    recompute();

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

      <div className="tb-longview-blocks">
        {data.blocks.map((block, i) => renderBlock(block, i))}
      </div>

      <Hair style={{ marginTop: 28, marginBottom: 16 }} />
      <div className="tb-longview-takeaway">
        <div className="tb-longview-takeaway-label">BANKER READ</div>
        <p>{data.banker_read}</p>
      </div>
    </section>
  );
}
