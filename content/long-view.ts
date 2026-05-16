import type { LongViewData } from "@/types/brief";

export const longView: LongViewData | null = {
  posted_at: "2026-05-12T00:30:00Z",
  title: "BNP government loosens six prudential rules in three months",
  lead: "Banking regulation across six dimensions has eased in the BNP government's first three months, reversing the Interim government's post-Hasina tightening.",
  blocks: [
    {
      kind: "stat",
      value: "6",
      label: "RULES EASED · FIRST 90 DAYS",
      body: "Across penal interest, loan exit, lending caps, conversion factors, pre-merger return, and NPL treatment — all six dimensions move in the same loosening direction.",
      tone: "bull",
    },
    {
      kind: "comparison",
      before_label: "Interim",
      after_label: "BNP-led",
      rows: [
        { title: "Penal interest on overdue loans", before: "1.5%", after: "0.5%", description: "Reduces punitive measures, loosens borrower burden.", tone: "bull" },
        { title: "Loan exit downpayment", before: "10%", after: "1–2%", description: "Significant barrier reduction for loan closure.", tone: "bull" },
        { title: "Single group lending cap (funded)", before: "15%", after: "25%", description: "Enhanced corporate access to credit.", tone: "bull" },
        { title: "Non-funded conversion factor", before: "0.50", after: "0.25", description: "Reduced risk weighting for non-cash instruments.", tone: "bull" },
        { title: "Pre-merger owner return", before: "BANNED", after: "AT 7.5%", description: "Selective re-entry permitted at a set threshold.", tone: "bull" },
        { title: "Non-performing loan (NPL) treatment", before: "Revealed", after: "Rescheduled", description: "Focus on repayment planning over public disclosure." },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "What to watch next",
      items: [
        { text: "**Provisioning rules.** Likely the next BNP move; current 1% general provision feels conservative given the rest of the loosening.", tone: "warn" },
        { text: "**Tier-1 bank quarterly results.** Q1 numbers from the four banks reporting late May will show whether the easing flows through to recovery rates.", tone: "bull" },
        { text: "Public disclosure norms could tighten again under opposition pressure. Watch the Parliamentary Standing Committee minutes." },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The pattern is consistent across all six rule changes: punitive measures soften, capacity opens, and disclosure-heavy obligations get replaced with operational ones. None of these changes individually moves the needle on a healthy bank's economics. Together, they widen the operating envelope for the entire industry.",
      ],
    },
  ],
  banker_read: "Treasury desks should anchor on the corridor, not the cut-off. If the corridor narrows in the next four weeks, the Sukuk curve repricing will be steep — re-hedge before the May 28 auction window.",
};
