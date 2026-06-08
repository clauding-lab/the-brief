import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-06-08T14:13:35Z",
  title: "Grameenphone and Robi's 2025 earnings diverged below the top line",
  lead: "Grameenphone's 2025 profit fell 18.6% to an eight-year low while Robi's rose 33.3% to a record — yet revenue barely moved at either operator, within ±0.4%. The swing sits below the top line: depreciation from new spectrum, finance costs and forex.",
  blocks: [
    {
      kind: "comparison",
      before_label: "GP",
      after_label: "Robi",
      rows: [
        {
          title: "Revenue",
          before: "Tk 15,806 cr",
          after: "Tk 9,992 cr",
          description: "GP's top line is roughly 1.6× Robi's.",
        },
        {
          title: "Profit after tax",
          before: "Tk 2,958 cr",
          after: "Tk 937 cr",
          description: "GP still banked ~3.2× Robi — but off an eight-year low.",
        },
        {
          title: "Profit growth · YoY",
          before: "−18.6%",
          after: "+33.3%",
          description: "An eight-year low against a record year.",
          tone: "bull",
        },
        {
          title: "Net profit margin",
          before: "18.7%",
          after: "9.4%",
          description: "GP converts revenue to profit at roughly 2× Robi's rate.",
          tone: "bear",
        },
        {
          title: "ARPU",
          before: "Tk 151",
          after: "Tk 145.8",
          description: "GP's premium shrank from Tk 13 to Tk 5.2 in a single year.",
        },
        {
          title: "Data penetration",
          before: "58%",
          after: "77.5%",
          description: "Robi's base is structurally more data-ready.",
          tone: "bull",
        },
        {
          title: "Dividend payout",
          before: "98.2%",
          after: "97.8%",
          description: "Both are near-total cash-return plays, not reinvestment stories.",
        },
      ],
    },
    {
      kind: "stat",
      value: "49",
      unit: "%",
      label: "GRAMEENPHONE RETURN ON EQUITY · FY2025",
      body: "Against Robi's 13.5%. GP turns shareholder equity into profit at roughly 3.6× Robi's rate — the \"bad year\" was a heavy-investment year, not a profitability collapse.",
      tone: "bull",
    },
    {
      kind: "bullet-list",
      eyebrow: "WHAT THE SCORECARD HIDES",
      items: [
        {
          text: "**Cost, not growth.** Profit swung roughly 90× more than revenue, which was flat at ±0.4% for both. Robi trimmed opex and forex losses through USD-debt repayment; GP absorbed depreciation from its 2.6GHz and incoming 700MHz spectrum, plus dollar-cost forex.",
        },
        {
          text: "**The eroding moat.** GP's ARPU premium over Robi collapsed from Tk 13 to Tk 5.2 in one year (−60%) as Robi lifted ARPU and subscribers together. GP calls the slide deliberate \"affordability\" — 2026 data conversion will show whether that is strategy or erosion.",
          tone: "bear",
        },
        {
          text: "**Mix is destiny.** Robi runs 77.5% data penetration to GP's 58%; GP still has ~35 million non-data subscribers to convert — real upside, but the slowest-monetising part of the base.",
        },
        {
          text: "**Q1 2026 moved the fight to the top line.** GP revenue −2% against Robi +8.1% — a 10-point gap in one quarter. Robi's profit jumped 85% on revenue-led growth; GP's rose 4.4% on cost discipline as its top line slipped.",
          tone: "warn",
        },
      ],
    },
  ],
  banker_read:
    "For equity desks, the \"Robi beat GP\" headline is a base-effect illusion: a 33% rise on a small base still leaves GP earning roughly 3.2× the profit and turning equity at 49% versus 13.5%. The real signal is quality of earnings — Robi defended margins through cost discipline and USD-debt deleveraging, a lever with a floor (you cannot cut selling-and-distribution costs 31% twice), while GP is carrying the depreciation of a full-spectrum build (700MHz, 2.6GHz) into a high-forex, high-rate window. For credit and counterparty desks, both names remain ~98%-payout cash-return plays rather than deleverage-and-reinvest stories — neither is building much equity cushion, and GP's heavier capex at least sits against the stronger balance sheet. The twelve-month tell is the top line: Q1 2026 already opened a 10-point revenue-growth gap (Robi +8.1%, GP −2%); if it holds two or three more quarters, GP's scale lead erodes from the top down and its \"cyclical dip\" read weakens. Watch GP's ARPU premium, now under Tk 6, and whether its 700MHz depreciation peaks and rolls off on the cyclical timeline GP is claiming.",
};
