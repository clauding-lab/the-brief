import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-06-06T04:55:11Z",
  title: "Seven banks' 2025 profits rest on deferred provisioning",
  lead: "Auditor-assessed accounts put seven listed banks in loss for 2025 once provisioning against their non-performing loans is fully recognised — each against a net profit reported on its published statements. The actual positions run from a Tk 620 cr loss at the smallest to Tk 84,508 cr at the largest.",
  blocks: [
    {
      kind: "comparison",
      before_label: "Reported",
      after_label: "Actual",
      rows: [
        {
          title: "Islami Bank",
          before: "Tk 136 cr",
          after: "−Tk 84,508 cr",
          description: "Largest Shariah-compliant bank; the widest gap of the seven.",
          tone: "bear",
        },
        {
          title: "Rupali Bank",
          before: "Tk 6.81 cr",
          after: "−Tk 14,000 cr",
          description: "The only state-owned commercial bank on the list.",
          tone: "bear",
        },
        {
          title: "Al-Arafah Islami Bank",
          before: "Tk 85.43 cr",
          after: "−Tk 5,306 cr",
          description: "Reported profit reverses to a multi-thousand-crore provisioned loss.",
          tone: "bear",
        },
        {
          title: "Standard Bank",
          before: "Tk 80 cr",
          after: "−Tk 5,200 cr",
          description: "Private commercial bank; book profit turns negative under full provisioning.",
          tone: "bear",
        },
        {
          title: "One Bank",
          before: "Tk 29.75 cr",
          after: "−Tk 3,340 cr",
          description: "Profit inverts once NPL provisioning is fully recognised.",
          tone: "bear",
        },
        {
          title: "UCB",
          before: "Tk 23.82 cr",
          after: "−Tk 3,278 cr",
          description: "United Commercial Bank — among the larger private lenders shown.",
          tone: "bear",
        },
        {
          title: "NRBC Bank",
          before: "Tk 13.27 cr",
          after: "−Tk 620 cr",
          description: "The smallest provisioned loss of the seven.",
          tone: "bear",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "THE DEFERRAL FACILITY",
      items: [
        {
          text: "**Provision deferral.** The seven use Bangladesh Bank's deferral facility to postpone provisioning against their non-performing loans, holding booked provisions below the level those loans imply.",
          tone: "warn",
        },
        {
          text: "**Paper profit.** With provisions deferred, each reports a net profit on its published accounts while the fully-provisioned position sits in loss.",
          tone: "bear",
        },
        {
          text: "**No dividend.** None can pay a cash dividend out of earnings that exist only before provisioning.",
          tone: "warn",
        },
        {
          text: "**Z-category.** Consecutive years without a dividend move a listed bank into the bourse's 'Z' category, its lowest trading tier.",
          tone: "bear",
        },
      ],
    },
  ],
  banker_read:
    "The divergence is a provisioning-recognition story, not a trading surprise: the deferral facility lets these names carry booked provisions below what their non-performing loan books require, so the published profit and the fully-provisioned result describe different banks. For equity desks, it caps the reliability of headline earnings across the seven — the dividend block, and the resulting move toward the bourse's 'Z' category, reads cleaner than the profit line. For credit and counterparty risk, the number that matters is the provision shortfall behind the loss column, which is where capital is exposed as the deferral unwinds; interbank lines and large-exposure limits to these names should be set against the actual position, not the reported one. The line to watch over the next several quarters is BB's timeline for withdrawing the facility and how much of each shortfall converts into a direct capital call — the banks carrying the widest gaps relative to their capital base face the sharpest adjustment.",
};
