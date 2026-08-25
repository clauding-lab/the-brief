import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-25T08:10:00Z",
  title: "Nine in Ten Economic Units Hold No TIN",
  lead: "Bangladesh has 1.17cr economic units. Only 10.22 lakh of them hold a Taxpayer Identification Number, and coverage thins sharply outside Dhaka and Chattogram.",
  blocks: [
    {
      kind: "stat",
      value: "10.22",
      unit: "LAKH",
      label: "TIN HOLDERS AGAINST 1.17CR ECONOMIC UNITS",
      body: "More than 90% of the country's economic units sit outside the direct-tax register. That register is also the documentary base a lender would normally underwrite against, so the gap is a credit-file problem before it is a revenue one.",
      tone: "bear",
    },
    {
      kind: "bar-chart",
      eyebrow: "SHARE OF ECONOMIC UNITS HOLDING A TIN, BY DIVISION",
      unit: "% of units",
      reference: { value: 8.7, label: "National 8.7%" },
      items: [
        { label: "Dhaka", value: 13.6, display: "13.6%", tone: "neu" },
        { label: "Chattogram", value: 10.4, display: "10.4%", tone: "neu" },
        { label: "Rajshahi", value: 5.5, display: "5.5%", tone: "bear" },
        { label: "Mymensingh", value: 4.7, display: "4.7%", tone: "bear" },
        { label: "Rangpur", value: 4.1, display: "4.1%", tone: "bear" },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "THE 1.17CR UNITS BY SIZE",
      items: [
        {
          text: "**Micro: 66.3 lakh.** The largest tier by some distance — more units than every other category combined.",
          tone: "neu",
        },
        {
          text: "**Cottage: 45.3 lakh.** Household-scale by definition. Cottage and micro together are 111.6 lakh units, or 95% of the entire base.",
          tone: "neu",
        },
        {
          text: "**Small: 4.9 lakh.** 4.2% of units, and with medium the whole of what the SME mandate covers.",
          tone: "neu",
        },
        { text: "**Medium: 40,000.** 0.3% of units.", tone: "neu" },
        {
          text: "**Large: 9,000.** 0.08% of units, and the corporate lending universe in its entirety.",
          tone: "neu",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The revenue side sets the arithmetic. Tax-to-GDP stands at 6.73% against a target of 10.7% by FY29, and the NBR's revenue target for FY27 is Tk 6.04 lakh cr. BIN coverage, the VAT-side registration, reaches 3.3% of economic units.",
        "Closing a gap of roughly 4 percentage points in three fiscal years, from a base where 10.22 lakh units carry a TIN, means the additional revenue has to come from units already inside the net, from higher effective rates, or from bringing new units in. The three routes land differently on a bank's book, and the composition above indicates which units are available to be brought in.",
      ],
    },
  ],
  banker_read:
    "For a lender the TIN gap is a documentation problem before it is a tax problem. A borrower without a TIN has no filed return to verify declared income against, which pushes SME and retail underwriting back onto bank-statement analysis, trade references and collateral — the three inputs hardest to standardise and easiest to dispute at recovery. The regional spread carries the same point into branch strategy: Dhaka's 13.6% is roughly three times Rangpur's 4.1%, so a growth plan weighted toward the divisions is also a plan weighted toward thinner documentation, and the risk-adjusted pricing should say so. If formalisation accelerates toward the FY29 target, both effects arrive together — filing and VAT compliance land on the customer's cash flow before the improved credit file shows up in a rating. Desks pricing multi-year SME facilities now should assume the cost lands first and the underwriting benefit lands later.",
};
