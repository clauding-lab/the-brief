import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-06-02T04:30:10Z",
  title: "Remittances climb 19% over eleven months of FY26",
  lead: "Workers' remittances accelerated through May 2026 — both the single month and the eleven-month fiscal-year tally landed well above a year ago.",
  blocks: [
    {
      kind: "bar-chart",
      eyebrow: "FY CUMULATIVE REMITTANCES · JUL–MAY · +19.09% YoY",
      unit: "US$ million",
      items: [
        { label: "FY2024-25", value: 27506.86, display: "27,506.86" },
        { label: "FY2025-26", value: 32756.78, display: "32,756.78", tone: "bull" },
      ],
    },
    {
      kind: "stat",
      value: "15.34",
      unit: "%",
      label: "MAY 2026 REMITTANCE GROWTH · YoY",
      body: "$3,425.03M in May 2026 against $2,969.46M a year earlier; the month's closing week (24–31 May) added $448.97M.",
      tone: "bull",
    },
  ],
  banker_read:
    "Sustained double-digit remittance growth is the quiet support under the taka and Bangladesh Bank's reserve position, and it feeds low-cost deposit growth for banks with strong NRB and remittance-channel franchises. At $32.8bn over eleven months and still accelerating, the inflow is doing more for system liquidity and the FX market right now than any single policy lever. Treasury desks should plan for continued remittance-driven dollar supply through the June fiscal-year close; ALCO can read the deposit-side tailwind as more structural than seasonal while it holds. The line to watch is the June print — whether the 15%-plus monthly pace sustains or eases as flows normalise.",
};
