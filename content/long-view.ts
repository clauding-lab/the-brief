import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-05T17:35:00Z",
  title: "Small Loans, Big Numbers, and the Default Barbell",
  lead: "Borrowers in default on loans under Tk 1 crore more than doubled in twelve months — 21.63 lakh to 45.43 lakh by end-March 2026, on Bangladesh Bank data reported by Prothom Alo on 1 August. Set against a 32.7% sector NPL rate and roughly Tk 5.83 lakh crore of implied impaired loans, the surge says more about household and micro-enterprise cash flow than about where the sector's losses actually sit.",
  blocks: [
    {
      kind: "stat",
      value: "45.43",
      unit: "LAKH",
      label: "DEFAULTED BORROWERS UNDER TK 1 CRORE · MAR 2026",
      body: "Up from 21.63 lakh a year earlier — a 110% rise, roughly 24 lakh newly defaulted households and micro-enterprises in a single year. Bangladesh Bank reads it as broad deterioration in retail credit quality, driven by living costs, household leverage and sluggish SME activity.",
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
      kind: "comparison",
      before_label: "Mar 2025",
      after_label: "Mar 2026",
      rows: [
        {
          title: "Under Tk 1 crore",
          before: "21,63,323",
          after: "45,43,485",
          description: "+110% — the surge band; 15.0% NPL rate on Tk 4.10 lakh crore outstanding",
          tone: "bear",
        },
        {
          title: "Tk 1 to 10 crore",
          before: "25,477",
          after: "28,501",
          description: "+12% — the cleanest large-ticket segment at a 26.5% NPL rate",
          tone: "neu",
        },
        {
          title: "Tk 10 to 20 crore",
          before: "3,336",
          after: "6,186",
          description: "+85% — fastest deterioration above Tk 1 crore; 45.0% NPL rate",
          tone: "bear",
        },
        {
          title: "Tk 20 to 30 crore",
          before: "1,125",
          after: "1,574",
          description: "+40% at a 36.0% NPL rate",
          tone: "bear",
        },
        {
          title: "Tk 30 to 40 crore",
          before: "605",
          after: "952",
          description: "+57% at a 39.0% NPL rate",
          tone: "bear",
        },
        {
          title: "Tk 40 to 50 crore",
          before: "392",
          after: "669",
          description: "+71% at a 45.0% NPL rate",
          tone: "bear",
        },
        {
          title: "Above Tk 50 crore",
          before: "1,478",
          after: "2,035",
          description: "+38% — 42.5% NPL rate on Tk 5.76 lakh crore outstanding",
          tone: "bear",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "THE THREE READS",
      items: [
        {
          text: "**Count is not value.** The 45.43 lakh sub-crore defaulters imply about Tk 61,500 crore of impaired money at a 15% band rate; the 2,035 names above Tk 50 crore imply about Tk 2.45 lakh crore — four times as much, at an average defaulted exposure of roughly Tk 120 crore against Tk 1.4 lakh.",
          tone: "warn",
        },
        {
          text: "**The salaried anomaly.** Consumer loans default at 7% against a 32.7% sector average. If the cost of living alone explained the surge, salaried books would be deteriorating too — income volatility, not income level, is doing the damage.",
          tone: "neu",
        },
        {
          text: "**Cottage is the sharpest signal.** 53% of cottage-industry lending is impaired, CMSME overall is at 34%, and medium enterprise at 38% — the stress is not confined to the smallest borrowers, and Krishi Bank now reports 38% of its book impaired.",
          tone: "bear",
        },
      ],
    },
  ],
  banker_read:
    "The actionable split for credit committees is underwriting basis, not ticket size. The salaried are still paying while the self-employed are not, so cash-flow-volatility screens beat income-level thresholds on retail and micro books — and support that arrives on time beats support that arrives large, which is the banks' own diagnosis of why small borrowers tip over. On portfolio strategy the barbell is the map: the Tk 1–10 crore commercial mid-market, at 26.5% impaired with defaulter growth of just 12%, is the one large-ticket segment where risk-adjusted growth still pencils, while every band above Tk 10 crore runs at 36% or worse. Provisioning and recovery capacity stay anchored to the two thousand names above Tk 50 crore, where the money is — but the 24 lakh new small defaulters are the early warning that household and micro cash flow broke in FY2025-26, and that is a deposit-quality and collections problem before it is ever a write-off problem.",
};
