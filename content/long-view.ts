import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-28T11:28:00Z",
  title: "The Data Rail Comes Before the Lending Model",
  lead: "Four markets built high-volume unsecured SME lending on four different data rails — China on payments and platform transaction data, India on Aadhaar e-KYC and GST e-invoicing, the United States on merchant acquiring data inside the platforms SMEs already sell through, and the United Kingdom on Open Banking and government guarantee schemes. Approval turnaround runs from seconds in China to one or two days in the UK.",
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
          description: "Filed statements and a submitted pack give way to transaction, invoice and platform flow observed as it happens.",
          tone: "neu",
        },
        {
          title: "The decision",
          before: "Credit officer",
          after: "Risk engine",
          description: "Judgement at file level becomes scoring at portfolio level, with approval measured in seconds to hours across all four markets.",
          tone: "bull",
        },
        {
          title: "The security",
          before: "Collateral",
          after: "Pre-approved limit",
          description: "The limit is set off observed business activity rather than off an asset pledged against it.",
          tone: "neu",
        },
        {
          title: "The offer",
          before: "Loan",
          after: "Embedded offer",
          description: "Credit is presented inside the wallet, marketplace or acquiring platform where the SME already transacts.",
          tone: "neu",
        },
        {
          title: "Repayment",
          before: "—",
          after: "Automated debit",
          description: "Auto-debit from bank, wallet or card receipts in every one of the four markets; the traditional chain has no equivalent stage.",
          tone: "bull",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "WHAT EACH MARKET ACTUALLY SOLVED",
      items: [
        {
          text: "**China — underwriting at scale off transaction data.** MYbank (Ant Group) and WeBank price off payments, wallet, e-commerce, tax-invoice and supply-chain data. RMB 10,000–5,000,000 unsecured, 3–12 months, approved in seconds to minutes, repaid by auto-debit from bank, wallet or platform receipts.",
          tone: "neu",
        },
        {
          text: "**India — the cost of acquisition and underwriting itself.** Aadhaar e-KYC, UPI payment history, GST e-invoicing, the Account Aggregator consent layer, bureau and bank data, and eMandate autopay. INR 100,000–5,000,000, 3–24 months, minutes to hours.",
          tone: "neu",
        },
        {
          text: "**United States — distribution.** Square Loans, Shopify Capital, PayPal Working Capital and OnDeck lend inside the platform the SME already sells through, repaid as a percentage of card sales. USD 5,000–500,000, 3–18 months, minutes to same day.",
          tone: "neu",
        },
        {
          text: "**United Kingdom — competition and tenor.** Open Banking under PSD2, bureau and financial data, and government guarantee schemes behind Funding Circle, iwoca, Tide, OakNorth and the challenger banks. GBP 10,000–2,000,000 over 6–60 months — the longest tenor and the largest unsecured ticket of the four.",
          tone: "neu",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "Read down the infrastructure column and these are not four credit products. They are four answers to the same prior question: what can a lender observe about a business without asking the business for anything. China observes payments and platform flow, India observes tax and bank data through a consented sharing layer, the United States observes merchant receipts at the acquirer, the United Kingdom observes bank accounts under a statutory access regime. The lending model in each case is downstream of whichever rail got built.",
        "Bangladesh has some of these rails and not others. NID-based e-KYC is live, MFS transaction data sits with the wallet operators, and the CIB and VAT registration are long established. What is absent is the consented data-sharing layer that lets one institution read a borrower's transaction and tax history held at another, and a working e-mandate standard that makes recurring collection routine rather than separately negotiated. Those are the two pieces India and the United Kingdom built before the lending volumes arrived, not after.",
      ],
    },
  ],
  banker_read:
    "The useful lesson here is a negative one. None of these four markets reached seconds-to-hours approval by writing a better credit policy; each got there because somebody first built a rail that let a lender see a business without interviewing it. That ordering decides how a Bangladeshi bank should spend the next three years. A digital SME journey layered over the same document pack, the same branch-level judgement and the same collateral test compresses the paperwork and leaves the unit economics exactly where they were — which is the reason small-ticket unsecured lending stays uneconomic here however good the front end looks. Two rails are worth pushing for at Bangladesh Bank and at association level rather than inside any single institution: consented data sharing on the Indian model, and an e-mandate standard for recurring collection. The first attacks underwriting cost, the second attacks recovery cost, and neither can be built by one bank acting alone. In the meantime the pragmatic version of the American model is already available — MFS and acquiring flows sit with counterparties a bank can contract with today, and lending against observed receipts through the platform that captures them is the one route to volume that does not wait on regulation. It is also the route that most changes what a credit committee is being asked to approve: a limit set by observed behaviour rather than a facility secured on an asset. That is a conversation worth having before the technology lands, not after.",
};
