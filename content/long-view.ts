import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-09-21T03:31:00Z",
  title: "Food's Share of Spending Rises as Income Falls",
  lead: "An IMF chart, built on USDA data, plots food spending as a share of GDP against food's share of total consumer spending. Poorer economies sit further up and further right on both scales.",
  blocks: [
    {
      kind: "bullet-list",
      eyebrow: "WHERE EACH INCOME GROUP SITS",
      items: [
        {
          text: "**Advanced economies hold the bottom-left corner.** Food takes roughly 5 to 22 percent of consumer spending in that group, on food outlays worth under about 13 percent of GDP.",
          tone: "neu",
        },
        {
          text: "**Emerging markets spread across the whole middle of the chart.** Their markers run from about 11 percent of consumer spending to above 40 percent, and the group overlaps the advanced cluster at one end and the low-income band at the other.",
          tone: "warn",
        },
        {
          text: "**Low-income developing countries occupy the top-right.** Every marker in that group sits above roughly 29 percent of consumer spending, and the highest of them approach 55 percent.",
          tone: "bear",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "A household that already spends half its money on food has no cheaper category to move into, so a price rise comes out of everything else it buys. The IMF places Bangladesh in the low-income group at the upper right of this chart. Food and beverages carry the largest single weight in the Bangladesh CPI basket, which is the same fact seen from the other side.",
      ],
    },
  ],
  banker_read:
    "Food inflation belongs in the credit process, not only in the macro commentary. A price move reaches disposable income before it reaches any borrower's file, and the thinnest-buffer books — retail, microfinance-linked exposure, small-ticket SME — feel it first. A risk team reading food prices only off the monthly CPI print is working from the slowest signal available.",
};
