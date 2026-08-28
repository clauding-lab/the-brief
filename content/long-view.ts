import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-08-25T08:10:00Z",
  title: "Nine in Ten Economic Units Hold No TIN",
  lead: "Bangladesh has 1.17cr economic units on the Bangladesh Bureau of Statistics' Economic Census 2024 count, as reported by The Daily Star. Only 10.22 lakh of them hold a Taxpayer Identification Number, and coverage thins sharply outside Dhaka and Chattogram.",
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
          text: "**Micro: 66.3 lakh.** It is the largest tier by some distance, with more units than every other category combined.",
          tone: "neu",
        },
        {
          text: "**Cottage: 45.3 lakh.** These are household-scale by definition. Cottage and micro together are 111.6 lakh units, or 95% of the entire base.",
          tone: "neu",
        },
        {
          text: "**Small: 4.9 lakh.** That is 4.2% of units, and with medium it is the whole of what the SME mandate covers.",
          tone: "neu",
        },
        { text: "**Medium: 40,000.** That is 0.3% of units.", tone: "neu" },
        {
          text: "**Large: 9,000.** That is 0.08% of units, and the whole of the corporate lending universe.",
          tone: "neu",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The revenue side sets the arithmetic. Tax-to-GDP stands at 6.73% against a target of 10.7% by FY29, and the NBR's revenue target for FY27 is Tk 6.04 lakh cr (Tk 6.04tn). Business Identification Number (BIN) coverage, the VAT-side registration, reaches 3.3% of economic units.",
        "The gap is roughly 4 percentage points over three fiscal years, from a base where 10.22 lakh units carry a TIN. The additional revenue can only come from units already inside the net, from higher effective rates, or from bringing new units in. The three routes land differently on a bank's book, and the composition above indicates which units are available to be brought in.",
      ],
    },
  ],
  banker_read:
    "For a lender the TIN gap cuts both ways. As a constraint, a borrower with no filed return leaves SME and retail underwriting resting on bank-statement analysis, trade references and collateral. Those are the inputs hardest to standardise and easiest to dispute at recovery. As an opportunity, the unregistered base is also the market. Cottage, micro, small and medium (CMSME) units total 116.9 lakh, or 99.9% of every economic unit in the country. Only 10.22 lakh units hold a TIN, and the VAT net is thinner still at 3.3%. The CMSME targets banks already carry are therefore being chased across a base where roughly nine counterparties in ten cannot yet be underwritten conventionally. Formalisation converts that overhang into addressable demand. The FY29 path implies a tax take around 59% higher relative to GDP than today's 6.73%, and that arithmetic cannot be delivered out of 10.22 lakh units alone. The regional spread shows where the conversion has to come from: Dhaka's 13.6% coverage is roughly three times Rangpur's 4.1%. The ground outside the two commercial centres carries the thinner documentation today and the larger share of the untapped base. Desks pricing multi-year CMSME facilities should expect the compliance cost to reach the customer before the improved credit file reaches the rating. They should be building acquisition and distribution now, against a documented borrower pool that on these numbers is an order of magnitude larger than the one they lend to today.",
};
