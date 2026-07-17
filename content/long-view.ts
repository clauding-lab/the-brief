import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-07-17T16:33:15Z",
  title: "Why Corporate Bangladesh Is Borrowing Offshore",
  lead: "Blue-chip Bangladeshi corporates are reaching for foreign-currency loans that price at 7–8% against 13–14% on comparable taka funding — a roughly 600 bps saving that is pulling names like PRAN-RFL, Meghna and Popular Pharma to IFC- and FMO-backed dollar facilities, even as private external debt sits near $20b as of March 2026.",
  blocks: [
    {
      kind: "stat",
      value: "~600",
      unit: "BPS",
      label: "COST GAP · OFFSHORE VS LOCAL BORROWING RATE",
      body: "Foreign-currency loans carry a 7–8% coupon versus 13–14% on comparable taka funding — roughly halving the cost of debt for corporates that can access offshore lenders.",
      tone: "bull",
    },
    {
      kind: "bar-chart",
      eyebrow: "RECENT APPROVALS · IFC-BACKED DOLLAR FACILITIES",
      unit: "$m",
      items: [
        { label: "Meghna", value: 80, display: "$80m", tone: "bull" },
        { label: "PRAN-RFL", value: 65, display: "$65m", tone: "bull" },
        { label: "Popular Pharma", value: 30, display: "$30m", tone: "bull" },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "THE TRADE-OFF",
      items: [
        { text: "**Lower cost.** Offshore coupons run 5–7 percentage points below taka funding, freeing cash flow for capex and working capital.", tone: "bull" },
        { text: "**Bigger tickets.** Development-finance lenders like IFC and FMO fund at a scale local balance sheets struggle to match on their own.", tone: "bull" },
        { text: "**Global credibility.** An IFC facility doubles as a due-diligence stamp that eases the next round of offshore fundraising.", tone: "bull" },
        { text: "**FX risk.** The loans are dollar-denominated — unhedged, a weaker taka inflates repayment in local terms and can erase the rate advantage.", tone: "bear" },
      ],
    },
  ],
  banker_read:
    "For corporate and treasury desks, the offshore pivot is rational arithmetic: at a 500–700 bps saving, a well-rated exporter or manufacturer with natural dollar earnings can cut funding costs sharply, and Bangladesh Bank's signalled easing of foreign-borrowing rules widens the door. The catch is currency. These are dollar liabilities against a taka that has been on a depreciating path, so the saving only holds for borrowers with matched foreign-currency revenue or a hedging line — for the rest, a 5–7% move in the taka can wipe out the rate advantage. Watch two things: whether BB's rule change broadens eligibility beyond the current blue-chip, IFC-vetted names, and how fast private external debt climbs from its ~$20b March-2026 base, since a rising unhedged stock lifts system-level FX and rollover risk that eventually lands on domestic lenders' credit books.",
};
