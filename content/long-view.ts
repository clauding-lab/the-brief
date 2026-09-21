import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-09-21T03:31:00Z",
  title: "Food's Share of Spending Rises as Income Falls",
  lead: "An IMF chart built on USDA data plots each economy's food spending as a share of GDP against food's share of total consumer spending. The two rise together across the sample, and low-income developing countries sit at the top-right corner of both scales.",
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
        "The two measures track each other closely, and the mechanism behind that is straightforward. A household that already spends half its money on food has no cheaper category to move into when food prices rise, so the increase comes out of everything else it buys. The same percentage move in food prices therefore transfers far more real income away from a household at the top-right of this chart than from one at the bottom-left.",
        "The IMF classifies Bangladesh among low-income developing countries, the group in the upper-right band. That placement sets the transmission path for a food price move: it reaches headline inflation first, real household income next, and the repayment behaviour of retail and small-ticket SME borrowers after that. It is the same fact the CPI shows from the other side, where food and beverages carry the largest single weight in the Bangladesh basket.",
      ],
    },
  ],
  banker_read:
    "The read for a Bangladeshi bank is that food inflation belongs in the credit process, not only in the macro commentary. Where food absorbs the share of spending this chart shows, a price move reaches disposable income before it reaches any borrower's file, and the books with the least buffer — retail, microfinance-linked exposure, small-ticket SME — feel it first. A risk team tracking food prices only through the monthly CPI print is working from the slowest signal available, because wholesale and import-cost data move earlier and are already published. Treasury has the same interest from the other direction, since a food shock that lands on household income also narrows the room Bangladesh Bank has to ease over the next few quarters.",
};
