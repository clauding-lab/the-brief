import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-06-12T14:39:24Z",
  title: "Bangladesh's FY27 budget, read as a credit file",
  lead: "Bangladesh's first budget under the elected government totals Tk 9.38 lakh crore — 13.7% of GDP, up 19% after two flat years — with a Tk 6.95 lakh crore revenue target and a 3.6%-of-GDP deficit, half financed externally. It pairs a deep tax-and-process reform layer with revenue, financing and delivery assumptions well above recent run-rates.",
  blocks: [
    {
      kind: "comparison",
      before_label: "Target",
      after_label: "Reality",
      rows: [
        {
          title: "NBR revenue growth",
          before: "~+40% needed",
          after: "9–12% run-rate",
          description: "FY27's revenue leap against NBR's historical pace.",
          tone: "bear",
        },
        {
          title: "External financing",
          before: "+Tk 1.16 lakh cr",
          after: "−Tk 7,677 cr",
          description: "Assumed net inflow versus the actual 9-month FY26 net outflow.",
          tone: "bear",
        },
        {
          title: "ADP delivery",
          before: "Tk 3.00 lakh cr",
          after: "40.7% used",
          description: "FY26 development spend executed through April.",
          tone: "bear",
        },
        {
          title: "Budget execution",
          before: "Tk 7.97 lakh cr",
          after: "Tk 6.31 lakh cr",
          description: "FY25's headline budget versus what was actually spent.",
          tone: "bear",
        },
      ],
    },
    {
      kind: "stat",
      value: "−2.64",
      unit: "%",
      label: "BANKING-SECTOR CAR · END-2025",
      body: "System capital is negative. Yet the budget's boldest bets — a Tk 60,000 cr subsidised-credit push and doubled consumer-loan limits — run through this balance sheet, with gross NPLs at 32.26% (end-March 2026) and a recapitalisation need near Tk 40,000 cr.",
      tone: "bear",
    },
    {
      kind: "bar-chart",
      eyebrow: "BUDGET SIZE · +19% AFTER TWO FLAT YEARS",
      unit: "Tk lakh cr",
      items: [
        { label: "FY24", value: 7.62, display: "7.62" },
        { label: "FY25", value: 7.97, display: "7.97" },
        { label: "FY26", value: 7.9, display: "7.90" },
        { label: "FY27", value: 9.38, display: "9.38", tone: "warn" },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "THE REFORM LAYER · AND HOW TO LEND",
      items: [
        {
          text: "**The zero-cost reforms matter most.** Appeal deposits cut from 10% to 1–3% (unfreezing disputed working capital), withholding tax made adjustable with refunds, 48-hour company registration with deemed approval, and repatriation up to Tk 100 cr without prior Bangladesh Bank sign-off.",
          tone: "bull",
        },
        {
          text: "**Cheapest SME money of the cycle.** The Tk 60,000 cr stimulus at a 6% interest subsidy puts effective rates below half of market; SME turnover is tax-free to Tk 50 lakh (Tk 70 lakh for women). The subsidy sets the price — underwriting decides whether it builds the economy or the FY29 NPL vintage.",
        },
        {
          text: "**Three dates decide the year.** July — can BB hold 10% while running a Tk 60,000 cr subsidised-credit package? September — the Q1 NBR run-rate (~Tk 50,000 cr a month needed against ~Tk 31,500 cr this year). October — external disbursements against the Tk 1.16 lakh cr assumption.",
          tone: "warn",
        },
        {
          text: "**The pragmatic read.** Back the reform layer, not the headline numbers; lend into the stimulus with FY29 underwriting, not FY27 optimism; re-test the frame against actuals, not announcements.",
        },
      ],
    },
  ],
  banker_read:
    "The budget reads better as a reform programme than as an arithmetic. For credit and ALCO desks, the operative fact is that its boldest demand-side bets — the Tk 60,000 cr subsidised-credit push, doubled consumer-loan limits, a near-doubled development programme — run through a banking system at negative aggregate capital (CAR −2.64%) and 32.26% gross NPLs, so the subsidy sets loan pricing but underwriting discipline, not the rate, decides whether this becomes growth or the FY29 NPL vintage. The financing math is the live risk: external inflows assumed at Tk 1.16 lakh crore ran net-negative through nine months of FY26, and any shortfall converts directly into government bank-borrowing that crowds the 6.5% private-credit envelope. The reform layer, by contrast, is real and low-cost — unfrozen appeal deposits, adjustable withholding, faster registration, easier repatriation — and is where the durable value sits. Watch three dates: July's BB policy statement (can it hold 10% alongside subsidised credit?), September's Q1 NBR run-rate (~Tk 50,000 cr a month needed against ~Tk 31,500 cr actual), and October's external disbursements — miss the last and banks fund the gap.",
};
