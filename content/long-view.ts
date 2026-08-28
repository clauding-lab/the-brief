import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-28T11:19:00Z",
  title: "CMSME Is Now the Cleaner Book, and the Smaller One",
  lead: "At 31 March 2026 the CMSME portfolio stood at 15.87% of total loans against a 25.50% regulatory target, down 0.97pp on the year and 0.89pp on the quarter. Over the same twelve months the CMSME classified ratio rose 2.10pp to 26.04% while the system-wide NPL ratio rose 8.13pp to 32.26%.",
  blocks: [
    {
      kind: "stat",
      value: "26.04",
      unit: "%",
      label: "CMSME CLASSIFIED RATIO · 31 MAR 2026",
      body: "A year ago CMSME's classified ratio of 23.94% sat marginally below the system's 24.13% — the two books were, on this measure, the same book. They are 6.22pp apart now, and the gap opened because the rest of the portfolio deteriorated close to four times faster.",
      tone: "bear",
    },
    {
      kind: "comparison",
      before_label: "Mar 2025",
      after_label: "Mar 2026",
      rows: [
        {
          title: "CMSME share of total loans",
          before: "16.84%",
          after: "15.87%",
          description: "Target 25.50%; the shortfall widened to 9.63pp, falling on both the year and the quarter.",
          tone: "bear",
        },
        {
          title: "CMS share of CMSME",
          before: "68.09%",
          after: "68.68%",
          description: "Floor of 50% cleared by 18.68pp — the only target with real headroom.",
          tone: "bull",
        },
        {
          title: "Women entrepreneur share",
          before: "6.45%",
          after: "7.28%",
          description: "Target 15%; less than half met, but the only line advancing on both the year and the quarter.",
          tone: "neu",
        },
        {
          title: "Cluster share of CMSME",
          before: "6.24%",
          after: "5.44%",
          description: "Target 10%; roughly half met and giving ground on both horizons, 0.79pp of it in the March quarter.",
          tone: "bear",
        },
        {
          title: "Manufacturing share",
          before: "36.61%",
          after: "34.96%",
          description: "Floor of 40% breached, and 1.66pp further from it than a year ago.",
          tone: "bear",
        },
        {
          title: "Service share",
          before: "19.36%",
          after: "20.11%",
          description: "Floor of 20% cleared this year by 0.11pp, though it slipped 0.53pp in the quarter.",
          tone: "bull",
        },
        {
          title: "Trade share of CMSME",
          before: "44.03%",
          after: "44.93%",
          description: "Ceiling of 40% exceeded by 4.93pp and still widening on both horizons.",
          tone: "bear",
        },
        {
          title: "CMSME classified ratio",
          before: "23.94%",
          after: "26.04%",
          description: "No regulatory target; up 2.01pp of its 2.10pp annual move in the March quarter alone.",
          tone: "bear",
        },
        {
          title: "System-wide NPL ratio",
          before: "24.13%",
          after: "32.26%",
          description: "No regulatory target; up 8.13pp in a year, the largest move anywhere in the table.",
          tone: "bear",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The composition targets are moving as a set rather than independently. Manufacturing fell through its 40% floor to 34.96% while trade pushed 4.93pp above its 40% ceiling to 44.93% — one shift read twice, as short-tenor trade exposure displaces term manufacturing exposure inside a pool that is itself contracting. Cluster lending, the hardest CMSME line to originate, gave up 0.79pp in a single quarter.",
        "Two of the seven policy targets are met, and both sit where the segment's own structure puts them. CMS at 68.68% reflects the small average ticket that defines cottage, micro and small lending; service cleared its floor by 0.11pp and gave back 0.53pp in the quarter, so it is met on the date and not much more than that. Women entrepreneur lending at 7.28% against a 15% target is the one line moving toward its mark on both horizons, and it is still less than half way there.",
      ],
    },
  ],
  banker_read:
    "The scorecard reads as a retreat from CMSME, and the credit numbers do not support one. The segment's classified ratio rose 2.10pp over the year against 8.13pp for the system, which puts whatever is driving the 32.26% headline substantially outside the CMSME book — and yet CMSME is the exposure being cut, by 0.89pp in the March quarter alone. For an SME business head that is an argument to defend the portfolio allocation at ALCO on relative asset quality rather than on the policy target, which at a 9.63pp shortfall and widening has stopped functioning as a constraint anybody is managing to. The composition question is the less comfortable one. Trade at 44.93% against a 40% ceiling means a book increasingly built on short-tenor, self-liquidating facilities: it turns faster, it flatters the near-term classified ratio, and it does nothing for the 40% manufacturing floor the same policy requires. A desk that lets trade carry the growth will meet its NPL comfort and miss its mandate, and the March quarter shows both happening at once. Watch the cluster line — down 0.79pp in three months — because it is where origination cost bites first, and its direction is the cleanest read on whether banks are still building CMSME capacity or simply running the existing book down.",
};
