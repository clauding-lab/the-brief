import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-16T12:42:00Z",
  title: "BNP government loosens six prudential rules in three months",
  lead: "Bangladesh's banking prudential frame has eased across six dimensions in the BNP government's first three months, reversing tightening the Interim government had introduced post-Hasina. The shifts touch penal-interest rates, the loan-exit downpayment, the single-group lending cap, the non-funded conversion factor, NPL treatment, and pre-merger ownership rules.",
  blocks: [
    {
      kind: "comparison",
      before_label: "Interim",
      after_label: "BNP-led",
      rows: [
        {
          title: "Penal interest on overdue loans",
          before: "1.5%",
          after: "0.5%",
          description: "Lower carry cost on delinquent paper; modest hit to penal-interest revenue, friction reduction in workouts.",
        },
        {
          title: "Loan-exit downpayment",
          before: "10%",
          after: "1–2%",
          description: "Far easier loan closures; correspondingly lower borrower skin in the exit.",
          tone: "bear",
        },
        {
          title: "Single-group lending cap (funded)",
          before: "15%",
          after: "25%",
          description: "Single-name concentration limit widens by two-thirds.",
          tone: "bear",
        },
        {
          title: "Non-funded conversion factor",
          before: "0.50",
          after: "0.25",
          description: "Halves the RWA loading on non-cash exposures (guarantees, LCs); directly relieves Tier-1 ratios.",
        },
        {
          title: "Pre-merger owner return",
          before: "BANNED",
          after: "AT 7.5%",
          description: "Selective re-entry permitted at a set threshold; previously prohibited outright.",
          tone: "bear",
        },
        {
          title: "Non-performing loan (NPL) treatment",
          before: "Revealed",
          after: "Rescheduled",
          description: "Stressed assets pulled behind a forbearance line rather than carried in public disclosure.",
          tone: "bear",
        },
      ],
    },
  ],
  banker_read: "This is a coordinated prudential loosening, not a tweak. The NPL-treatment shift and the NCF cut do the heaviest lifting on reported numbers — Tier-1 ratios improve by RWA construction, headline NPLs improve by recognition rule rather than underlying asset quality. Credit committees should expect single-name concentrations to widen at the system level; risk teams should price the next stress cycle assuming the buffer the Interim built has been substantially given back. Treasury desks watching peer disclosures will see optical improvement diverge from underlying portfolio health — calibrate your own view accordingly.",
};
