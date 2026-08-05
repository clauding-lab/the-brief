import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-05T17:35:00Z",
  title: "Small Loans, Big Numbers, and the Default Barbell",
  lead: "Borrowers in default on loans under Tk 1 crore more than doubled in a year — 21.63 lakh to 45.43 lakh by end-March 2026, per Bangladesh Bank data reported by Prothom Alo. The surge is a signal about household and micro-enterprise cash flow, not about where the sector's losses sit.",
  blocks: [
    {
      kind: "stat",
      value: "45.43",
      unit: "LAKH",
      label: "DEFAULTED BORROWERS UNDER TK 1 CRORE · MAR 2026",
      body: "Up from 21.63 lakh a year earlier — roughly 24 lakh newly defaulted households and micro-enterprises. Bangladesh Bank blames living costs, household leverage and sluggish SME activity.",
      tone: "bear",
    },
    {
      kind: "bar-chart",
      eyebrow: "NPL RATE BY TICKET BAND · END-MARCH 2026",
      unit: "%",
      reference: { value: 32.7, label: "Sector 32.7%" },
      items: [
        { label: "Under Tk 1 cr", value: 15.0, display: "15.0%", tone: "warn" },
        { label: "Tk 1–10 cr", value: 26.5, display: "26.5%", tone: "bull" },
        { label: "Tk 10–20 cr", value: 45.0, display: "45.0%", tone: "bear" },
        { label: "Tk 20–30 cr", value: 36.0, display: "36.0%", tone: "bear" },
        { label: "Tk 30–40 cr", value: 39.0, display: "39.0%", tone: "bear" },
        { label: "Tk 40–50 cr", value: 45.0, display: "45.0%", tone: "bear" },
        { label: "Above Tk 50 cr", value: 42.5, display: "42.5%", tone: "bear" },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "THE THREE READS",
      items: [
        {
          text: "**Count is not value.** The 45.43 lakh small defaulters imply about Tk 61,500 crore of impaired money; the 2,035 names above Tk 50 crore imply about Tk 2.45 lakh crore — four times as much.",
          tone: "warn",
        },
        {
          text: "**The salaried anomaly.** Consumer loans default at 7% against 32.7% sector-wide — income volatility, not income level, is doing the damage.",
          tone: "neu",
        },
        {
          text: "**The clean middle.** Tk 1–10 crore runs at 26.5% with defaulter growth of just 12%; at the other pole, cottage industry is 53% impaired.",
          tone: "bear",
        },
      ],
    },
  ],
  banker_read:
    "Underwrite for cash-flow volatility, not income level — the salaried are paying, the self-employed are not. The Tk 1–10 crore commercial mid-market (26.5% impaired, defaulters up just 12%) is the one large-ticket segment where risk-adjusted growth still pencils. The money stays with the two thousand names above Tk 50 crore, but the 24 lakh new small defaulters mark FY2025-26 as the year household and micro cash flow broke — a collections and deposit-quality problem before it is a write-off problem.",
};
