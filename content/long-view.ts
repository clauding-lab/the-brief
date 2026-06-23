import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-06-23T09:32:00Z",
  title: "The Core Banking Software Running Bangladesh's Banks",
  lead: "Bangladesh's banks run a fragmented mix of core banking systems — no single platform holds more than 16% of the install base, foreign vendors dominate the market structure, yet a homegrown system, Bank Ultimus, leads on sheer adoption. The split runs along bank size and budget: global platforms at the large private and Islamic banks, local systems at the cost-sensitive rest.",
  blocks: [
    {
      kind: "bar-chart",
      eyebrow: "CBS INSTALL BASE · SHARE OF BANKS USING",
      unit: "% of banks",
      items: [
        { label: "Bank Ultimus (local)", value: 16, display: "16%", tone: "bull" },
        { label: "Temenos T24 (Transact)", value: 14, display: "14%" },
        { label: "Oracle FLEXCUBE", value: 13, display: "13%" },
        { label: "Flora Bank (local)", value: 13, display: "13%" },
        { label: "Finacle (Infosys)", value: 7, display: "7%" },
        { label: "Ababil", value: 5, display: "5%" },
        { label: "Misys Equation / Finastra", value: 5, display: "5%" },
        { label: "iStelar", value: 5, display: "5%" },
        { label: "Others (eIBS, PIBS, Kastle, Intellect, Silverlake…)", value: 17, display: "17%" },
      ],
    },
    {
      kind: "comparison",
      before_label: "Global",
      after_label: "Bank Ultimus",
      rows: [
        {
          title: "Global popularity",
          before: "★★★★★",
          after: "★★★",
          description: "Temenos, FLEXCUBE and Finacle are global standards; Ultimus is Bangladesh-only.",
          tone: "bear",
        },
        {
          title: "Local support",
          before: "★★★",
          after: "★★★★★",
          description: "Homegrown vendor — on-the-ground support and faster turnaround.",
          tone: "bull",
        },
        {
          title: "Cost",
          before: "High",
          after: "Lower",
          description: "Lower licence and implementation cost than the global platforms.",
          tone: "bull",
        },
        {
          title: "Islamic banking",
          before: "★★★★",
          after: "★★★★",
          description: "T24 & FLEXCUBE rate ★★★★, Finacle ★★★; Ultimus matches the top tier.",
          tone: "neu",
        },
        {
          title: "Large-bank suitability",
          before: "★★★★★",
          after: "★★★★",
          description: "Globals scale to the biggest books; Ultimus sits just behind.",
          tone: "neu",
        },
        {
          title: "Small / medium-bank fit",
          before: "★★★",
          after: "★★★★★",
          description: "Ultimus is the best fit for cost-sensitive mid-size banks.",
          tone: "bull",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "MARKET STRUCTURE · BY ORIGIN",
      items: [
        { text: "**Foreign solutions — 46%.** The single largest category; global vendors still dominate the market structure.", tone: "neu" },
        { text: "**Local solutions — 36%.** Homegrown platforms, led by Bank Ultimus and Flora Bank.", tone: "bull" },
        { text: "**Joint-venture — 11%.** Foreign cores localised through Bangladeshi partners.", tone: "neu" },
        { text: "**In-house developed — 7%.** Banks running their own builds.", tone: "neu" },
      ],
    },
  ],
  banker_read:
    "For a bank scoping a core-banking RFP or a digital-transformation budget, the choice is now a segmentation decision, not a prestige one. Tier-1 and Islamic banks pay up for Temenos, FLEXCUBE or Finacle's scale, ATM/mobile integration and global support — but a locally-built platform topping the install base signals that for mid-size, cost-sensitive banks, local support, Bangladesh Bank compliance and lower total cost of ownership increasingly outweigh the global brand. The fragmentation — the leader at just 16%, a 17% long tail — also means vendor lock-in is weaker than it looks: useful leverage on price and SLAs at renewal, and it leaves open whether Bank Ultimus's share keeps climbing as digital-banking feature parity narrows.",
};
