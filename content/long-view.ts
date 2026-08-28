import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-28T11:28:00Z",
  title: "The Data Rail Comes Before the Lending Model",
  lead: "Four markets built high-volume unsecured SME lending on four different data rails: payments and platform data in China, Aadhaar e-KYC and GST e-invoicing in India, merchant acquiring data in the United States, Open Banking in the United Kingdom. Approval runs from seconds to two days, unsecured tickets from INR 100,000 to GBP 2,000,000.",
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
          description: "A submitted pack gives way to transaction, invoice and platform flow observed as it happens.",
          tone: "neu",
        },
        {
          title: "The decision",
          before: "Credit officer",
          after: "Risk engine",
          description: "File-level judgement becomes portfolio-level scoring; approval lands in seconds to hours in all four markets.",
          tone: "bull",
        },
        {
          title: "The security",
          before: "Collateral",
          after: "Pre-approved limit",
          description: "The limit is set off observed business activity, not off an asset pledged against it.",
          tone: "neu",
        },
        {
          title: "The offer",
          before: "Loan",
          after: "Embedded offer",
          description: "Credit appears inside the wallet, marketplace or acquiring platform the SME already uses.",
          tone: "neu",
        },
        {
          title: "Repayment",
          before: "—",
          after: "Automated debit",
          description: "Auto-debit from bank, wallet or card receipts in all four; the traditional chain has no such stage.",
          tone: "bull",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "WHAT EACH MARKET ACTUALLY SOLVED",
      items: [
        {
          text: "**China — underwriting at scale.** MYbank and WeBank price off payments, wallet, e-commerce, tax-invoice and supply-chain data. RMB 10,000–5,000,000, 3–12 months, seconds to minutes.",
          tone: "neu",
        },
        {
          text: "**India — the cost of acquisition and underwriting.** Aadhaar e-KYC, UPI history, GST e-invoicing, the Account Aggregator consent layer, eMandate autopay. INR 100,000–5,000,000, 3–24 months, minutes to hours.",
          tone: "neu",
        },
        {
          text: "**United States — distribution.** Square, Shopify Capital, PayPal Working Capital and OnDeck lend inside the platform the SME sells through, repaid as a share of card sales. USD 5,000–500,000, 3–18 months.",
          tone: "neu",
        },
        {
          text: "**United Kingdom — competition and tenor.** Open Banking under PSD2 plus government guarantee schemes, behind Funding Circle, iwoca, Tide and OakNorth. GBP 10,000–2,000,000 over 6–60 months, the longest tenor and largest ticket of the four.",
          tone: "neu",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "These are not four credit products. They are four answers to one prior question: what can a lender observe about a business without asking the business for anything. China observes platform flow, India tax and bank data through a consented sharing layer, the United States merchant receipts at the acquirer, the United Kingdom bank accounts under a statutory access regime. The lending model follows whichever rail got built.",
        "Bangladesh is further along than the comparison implies, and stuck somewhere else. NID-based e-KYC is live, the CIB and VAT registration are established, and direct debit instructions already run on bank accounts — the collection mandate exists. Two things it does not do: it does not reach MFS wallets, where much of small-business cash actually moves, and a failed direct debit carries none of the consequences a dishonoured cheque carries under the Negotiable Instruments Act. The missing rail is not the mandate. It is enforceability, and the consented data-sharing layer that would let one institution read a borrower's history held at another.",
      ],
    },
  ],
  banker_read:
    "The lesson is a negative one. None of these markets reached seconds-to-hours approval by writing a better credit policy; each first built a rail that let a lender see a business without interviewing it. A digital SME journey laid over the same document pack, the same branch judgement and the same collateral test compresses paperwork and leaves the unit economics where they were. Two things are worth pushing at Bangladesh Bank and association level rather than inside any one institution: consented data sharing on the Indian model, which attacks underwriting cost, and statutory consequence behind a dishonoured direct debit, which attacks recovery cost. A mandate a borrower can ignore without penalty is a convenience, not a security. Until that changes the American route is the one available now — MFS and acquiring flows sit with counterparties a bank can contract with today, and lending against receipts through the platform that captures them waits on no regulation. It does change what a credit committee is approving: a limit set by observed behaviour rather than a facility secured on an asset. Settle that argument before the technology lands, not after.",
};
