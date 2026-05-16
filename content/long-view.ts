import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data, commit, and
// let the user preview on a Vercel branch deployment before merging to main.
// See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-16T10:31:00Z",
  title: "BNP government loosens six prudential rules in three months",
  lead: "Bangladesh's banking prudential frame has eased across six dimensions in the BNP government's first three months, reversing tightening the Interim government had introduced post-Hasina. The shifts touch penal-interest rates, the loan-exit downpayment, the single-group lending cap, the non-funded conversion factor, NPL treatment, and pre-merger ownership rules.",
  body_paragraphs: [
    "Three settings move directly in favour of borrowers and lenders' new-credit appetite. Penal interest on overdue loans drops from 1.5% to 0.5%; the loan-exit downpayment falls from 10% to 1–2%; the single-group lending cap (funded) widens from 15% to 25%. Together this materially eases the cost of carrying delinquent paper, the friction of closing out troubled accounts, and the room to concentrate exposure on a single group.",
    "Three further settings reshape capital, asset quality, and ownership. The non-funded conversion factor is cut from 0.50 to 0.25 — halving the RWA loading on non-cash exposures like guarantees and LCs, which directly relieves Tier-1 ratios for trade-finance-heavy books. NPL treatment moves from 'Revealed' to 'Rescheduled' — pulling stressed assets back behind a forbearance line rather than carrying them in the public stack. And pre-merger owners, previously banned outright, may now re-enter at a 7.5% threshold.",
  ],
  chart_spec: null,
  banker_read: "This is a coordinated prudential loosening, not a tweak. The NPL-treatment shift and the NCF cut do the heaviest lifting on reported numbers — Tier-1 ratios improve by RWA construction, headline NPLs improve by recognition rule rather than underlying asset quality. Credit committees should expect single-name concentrations to widen at the system level; risk teams should price the next stress cycle assuming the buffer the Interim built has been substantially given back. Treasury desks watching peer disclosures will see optical improvement diverge from underlying portfolio health — calibrate your own view accordingly.",
};
