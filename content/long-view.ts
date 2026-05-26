import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-26T07:02:00Z",
  title: "BB's Tk 60,000 cr stimulus leans 68% on commercial-bank refinancing",
  lead: "Bangladesh Bank announced the package on 24 May 2026. Of the Tk 60,000 cr headline, only Tk 19,000 cr (32%) comes from BB's own balance sheet — the remaining Tk 41,000 cr is refinancing intermediated through commercial banks' excess liquidity. The single largest bucket, Tk 20,000 cr for reopening shuttered factories, is entirely commercial-bank funded. Stated employment target: 2.5 million jobs.",
  blocks: [
    {
      kind: "stat",
      value: "60,000",
      unit: "CR",
      label: "STIMULUS PACKAGE · BB ANNOUNCED 24 MAY 2026",
      body: "Tk 41,000 cr from commercial-bank excess liquidity (refinancing); Tk 19,000 cr from BB's own funds. Targeting 2.5 million jobs across factory revival, agriculture, exports, and CMSME.",
    },
    {
      kind: "bar-chart",
      eyebrow: "WHERE THE TK 60,000 CR GOES",
      unit: "Tk crore",
      items: [
        { label: "Closed factories", value: 20000, display: "20,000", tone: "warn" },
        { label: "Agriculture", value: 13000, display: "13,000" },
        { label: "Exports", value: 12000, display: "12,000" },
        { label: "CMSME / cottage", value: 10000, display: "10,000" },
        { label: "Jobs & social", value: 5000, display: "5,000" },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The funding split is the read. Tk 41,000 cr — the refinancing fund — sits as a directive to commercial banks to deploy their excess liquidity into five buckets: closed factories (Tk 20,000 cr), agriculture (Tk 10,000 cr), CMSMEs (Tk 5,000 cr), export diversification (Tk 3,000 cr), and a North Bengal agricultural hub (Tk 3,000 cr). BB orchestrates; commercial banks carry the credit risk.",
        "BB's own Tk 19,000 cr is concentrated in export-earning sectors — pre-shipment credit refinancing (Tk 5,000 cr), leather and footwear (Tk 2,000 cr), frozen shrimp and fish (Tk 2,000 cr) — alongside cottage industries (Tk 5,000 cr) and the smaller social buckets (youth, rural, green, overseas, startup, creative). The pattern is asymmetric: BB de-risks its own balance sheet by lending against forex receivables, while the larger commercial-bank exposure runs into revival lending where collateral is thin and the firms have already failed once.",
      ],
    },
  ],
  banker_read: "For credit committees: the Tk 20,000 cr closed-factory allocation is the line to watch. These are firms that previously stopped operating — refinancing applications will arrive with weak collateral, a track record of distress, and pressure from BB on participation. Provisioning policies for this bucket should be tightened pre-emptively; ECL modelling should not treat refinanced exposures as new originations. Treasury desks should expect the asset side to lengthen and skew toward higher-yield corporate paper as the Tk 41,000 cr refinancing pool deploys. For ALCO: the BB-funded chunk (Tk 19,000 cr) cleanly targets export-earning sectors with Tk 9,000 cr in foreign-currency-generating exposures — that's BB managing its own balance sheet risk by exposure to forex receivables, not domestic credit. The 2.5 million employment target should be discounted by historical overshoot on prior BB stimulus rounds; the credible read is closer to 60-70% of headline. The package is real money. How much of it shows up as performing credit a year from now is the only question that matters.",
};
