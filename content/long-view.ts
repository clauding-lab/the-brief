import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-28T11:28:00Z",
  title: "The Data Rail Comes Before the Lending Model",
  lead: "Four markets built high-volume unsecured SME lending on four different data rails. Approval runs from seconds in China to one or two days in the United Kingdom, which also carries the longest tenor at 6–60 months.",
  blocks: [
    {
      kind: "comparison",
      before_label: "Traditional",
      after_label: "Next-gen",
      rows: [
        {
          title: "The credit input",
          before: "Documents",
          after: "Real-time data",
          description: "A submitted document pack gives way to observed transaction flow.",
          tone: "neu",
        },
        {
          title: "The decision",
          before: "Credit officer",
          after: "Risk engine",
          description: "Approval lands in seconds to hours in all four markets.",
          tone: "bull",
        },
        {
          title: "The security",
          before: "Collateral",
          after: "Pre-approved limit",
          description: "The limit follows business activity, not a pledged asset.",
          tone: "neu",
        },
        {
          title: "The offer",
          before: "Loan",
          after: "Embedded offer",
          description: "Credit appears inside the platform the SME already uses.",
          tone: "neu",
        },
        {
          title: "Repayment",
          before: "—",
          after: "Automated debit",
          description: "The traditional chain has no equivalent stage.",
          tone: "bull",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "WHAT EACH MARKET SOLVED",
      items: [
        {
          text: "**China solved underwriting at scale.** MYbank and WeBank price off payments, platform and tax-invoice data. Tickets run RMB 10,000–5,000,000, approved in seconds to minutes.",
          tone: "neu",
        },
        {
          text: "**India solved acquisition cost.** Aadhaar e-KYC, UPI history, GST e-invoicing and the Account Aggregator consent layer carry the file. Tickets run INR 100,000–5,000,000, approved in minutes to hours.",
          tone: "neu",
        },
        {
          text: "**The United States solved distribution.** Square, Shopify Capital and PayPal Working Capital lend inside the platform the merchant already sells through, collecting from card receipts. Tickets run USD 5,000–500,000.",
          tone: "neu",
        },
        {
          text: "**The United Kingdom solved tenor.** Open Banking under PSD2 sits behind Funding Circle, iwoca and OakNorth. Tickets run GBP 10,000–2,000,000 over 6–60 months, the longest of the four.",
          tone: "neu",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "Bangladesh has more of this rail than the comparison implies. NID-based e-KYC is live, the CIB and VAT registration are established, and direct debit instructions already run on bank accounts. Two gaps remain. The mandate does not reach MFS wallets, where much of small-business cash moves, and a failed direct debit carries none of the consequence a dishonoured cheque carries under the Negotiable Instruments Act.",
      ],
    },
  ],
  banker_read:
    "None of these markets reached seconds-to-hours approval by writing a better credit policy. Each first built a rail that let a lender see a business without interviewing it. A digital journey laid over the same document pack and the same collateral test compresses paperwork and leaves the unit economics unchanged. Two things are worth pushing at Bangladesh Bank and association level: consented data sharing, which attacks underwriting cost, and statutory consequence behind a dishonoured direct debit, which attacks recovery cost. The American route needs neither — lending against receipts through the platform that captures them waits on no regulation.",
};
