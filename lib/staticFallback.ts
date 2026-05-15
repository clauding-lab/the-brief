import type { BriefPayload } from "@/types/brief";

/**
 * Issue 87 fallback. Used only if (a) the page hasn't fetched yet and
 * (b) localStorage cache is empty. Once Supabase RPC returns Issue 88+
 * the user sees that instead.
 */
export const STATIC_FALLBACK: BriefPayload = {
  brief: {
    issue_no: 87,
    volume: 1,
    brief_date: "2026-04-20",
    read_minutes: 15,
    cover_metric: {
      label: "NPL Ratio · Q4 2025",
      value: "35.73%",
      sub: "Tk 5.57 lakh-cr defaulted",
      tone: "bear",
      section_slug: "banking",
      as_of: "Q4 2025 · published 18 Apr 2026",
    },
    published_at: "2026-04-20T08:00:00+06:00",
  },
  sections: [
    {
      slug: "snapshot", ord: 1, title: "Snapshot", group_key: "overview",
      verdict: "Risk-on with caveats", verdict_tone: "neu", banker_read: null,
      metrics: [
        { label: "USD / BDT", value: "122.70", sub: "BB resumes buying", tone: "warn", is_snapshot: true, spark: [122.40, 122.50, 122.55, 122.60, 122.65, 122.70, 122.70], delta: "+0.05", delta_pct: "+0.04%", changed: true },
        { label: "DSEX", value: "5,219.74", sub: "−54.77 from 52-w high", tone: "bear", is_snapshot: true, spark: [5470, 5380, 5310, 5260, 5240, 5220, 5219], delta: "−12.40", delta_pct: "−0.24%", changed: true },
        { label: "91-d T-Bill", value: "9.78%", sub: "Softening", tone: "bull", is_snapshot: true, spark: [10.40, 10.20, 10.05, 9.95, 9.88, 9.82, 9.78], delta: "−4 bp", delta_pct: "−0.41%", changed: true },
        { label: "Brent", value: "$90.38", sub: "−9% d/d · Hormuz open", tone: "bull", is_snapshot: true, spark: [128, 121, 113, 104, 97, 93, 90.38], delta: "−$8.92", delta_pct: "−9.0%", changed: true },
        { label: "Gold (22K bhori)", value: "2,50,193", sub: "Safe-haven elevated", tone: "warn", is_snapshot: true, spark: [240, 242, 245, 247, 249, 250, 250.193], delta: "+1,420", delta_pct: "+0.57%", changed: true },
        { label: "Mar Remittance", value: "$3.755B", sub: "All-time monthly record", tone: "bull", is_snapshot: true, spark: [2.6, 2.7, 2.9, 3.1, 3.3, 3.5, 3.755], delta: "+$255M", delta_pct: "+7.3%", changed: false },
      ],
      news: [], series: [], notes: [],
    },
    {
      slug: "headlines", ord: 2, title: "Headlines", group_key: "overview",
      verdict: "Oil down, NPLs up, remittance breaks records", verdict_tone: "neu", banker_read: null,
      metrics: [], series: [], notes: [],
      news: [
        { headline: "Brent crashes 9% to $90.38 as Hormuz reopens", detail: "Saudi-Iran ceasefire signals hold; tankers cleared 18 Apr.", source: "Bloomberg", published_at: "2026-04-19", tone: "bull", changed: true },
        { headline: "NPL ratio prints record 35.73% — Tk 5.57 lakh-cr defaulted", detail: "Q4 2025 BB data; 5 SCBs hold 62% of stock.", source: "BB · Q4 stat bulletin", published_at: "2026-04-18", tone: "bear", changed: true },
        { headline: "March remittance hits all-time monthly $3.755B", detail: "Eid effect + formal-channel premium; cumulative FY +18%.", source: "Bangladesh Bank", published_at: "2026-04-17", tone: "bull", changed: true },
        { headline: "BB resumes USD purchases at Tk 122.75 after 6-wk pause", detail: "$70 mn lifted on 15 Apr; reserve build resumes.", source: "The Daily Star", published_at: "2026-04-15", tone: "bull" },
      ],
    },
    {
      slug: "bb", ord: 3, title: "Bangladesh Bank", group_key: "banking",
      verdict: "Holding; data-dependent", verdict_tone: "neu",
      banker_read: {
        verdict: "Holding rates while NPLs print 35.73% is a controlled bleed — credible until July, untenable after.",
        watch: ["Q1 NPL print due 28 Apr", "IMF Article-IV mission w/c 12 May"],
        risk: ["Premature SDF cut → taka pressure", "Brent re-spike if Hormuz ceasefire fails"],
        runway: { value: "10", unit: "weeks of policy runway before July MPC" },
      },
      metrics: [
        { label: "Repo", value: "10.00%", sub: "Held since Feb", tone: "neu" },
        { label: "SDF", value: "8.50%", sub: "Floor unchanged", tone: "neu" },
        { label: "CRR", value: "4.00%", sub: "Stable", tone: "neu" },
        { label: "Pvt-credit gr.", value: "7.4%", sub: "Below 8.5% target", tone: "warn" },
      ],
      series: [], notes: [],
      news: [
        { headline: "BB holds policy rates at April MPC; July review next", source: "BB press", published_at: "2026-04-16", tone: "neu" },
      ],
    },
    {
      slug: "banking", ord: 4, title: "Banking Sector", group_key: "banking",
      verdict: "Stress accelerating", verdict_tone: "bear", weight: 2,
      banker_read: {
        verdict: "NPLs at 35.73% are not a headline — they are the headline. Five SCBs carry the system's tail risk.",
        watch: ["SCB recapitalisation timeline", "Provisioning shortfall disclosure"],
        risk: ["Hidden losses in restructured loans", "Capital adequacy breach at 2 SCBs"],
      },
      metrics: [
        { label: "NPL Ratio", value: "35.73%", sub: "Q4 2025 · record", tone: "bear", changed: true },
        { label: "Defaulted Loans", value: "Tk 5.57 L-cr", sub: "+11.8% q/q", tone: "bear", changed: true },
        { label: "CAR (system)", value: "11.2%", sub: "Above 10% min", tone: "neu" },
      ],
      series: [], notes: [],
      news: [
        { headline: "NPL ratio prints 35.73%, a system record", source: "BB · Q4 bulletin", published_at: "2026-04-18", tone: "bear", changed: true },
      ],
    },
  ],
  _source: "static",
};
