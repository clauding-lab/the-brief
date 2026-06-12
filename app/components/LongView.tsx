"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { Block, LongViewData } from "@/types/brief";
import { Hair } from "./Hair";
import { formatLongViewEyebrow } from "@/lib/format";
import { LongViewProse } from "./LongViewProse";
import { LongViewComparison } from "./LongViewComparison";
import { LongViewStat } from "./LongViewStat";
import { LongViewBulletList } from "./LongViewBulletList";
import { LongViewBarChart } from "./LongViewBarChart";

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
    case "bar-chart":
      return <LongViewBarChart key={index} block={block} />;
  }
}

// Group a `stat` immediately followed by a `bar-chart` into a side-by-side
// pair (v1.6.0): stat left, compact chart right. All other blocks render
// full-width in sequence. Pairing is driven purely by block order — no
// layout fields in the pin data, per the Long View contract.
function renderBlocks(blocks: Block[]): ReactNode[] {
  const out: ReactNode[] = [];
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i];
    const next = blocks[i + 1];
    if (block.kind === "stat" && next && next.kind === "bar-chart") {
      out.push(
        <div className="tb-longview-pair" key={`pair-${i}`}>
          {renderBlock(block, i)}
          {renderBlock(next, i + 1)}
        </div>
      );
      i++;
    } else {
      out.push(renderBlock(block, i));
    }
  }
  return out;
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
        {renderBlocks(data.blocks)}
      </div>

      <Hair style={{ marginTop: 28, marginBottom: 16 }} />
      <div className="tb-longview-takeaway">
        <div className="tb-longview-takeaway-label">BANKER READ</div>
        <p>{data.banker_read}</p>
      </div>
    </section>
  );
}
