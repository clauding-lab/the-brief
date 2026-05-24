import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-24T07:14:00Z",
  title: "BB picked the wrong ruler for bank cash dividends",
  lead: "BB SPCD Circular No. 06 (23 May 2026) gates any cash dividend on Tk 2,000 cr in paid-up capital. Of the 11 largest listed banks, only NBL (Tk 3,220 cr) and BRAC Bank (Tk 2,290 cr) clear the line — and NBL's paid-up is roughly equal to its Tk 3,200 cr bad-loan book. Section 23 of the Income Tax Act 2023 then layers a 10% additional tax on any of the nine blocked banks that issue stock dividends exceeding cash, or no cash at all.",
  blocks: [
    {
      kind: "stat",
      value: "2,000",
      unit: "CR",
      label: "PAID-UP CAPITAL FLOOR · BB CASH-DIVIDEND GATE",
      body: "Banks below the Tk 2,000 cr line cannot declare any cash dividend; those above are capped at 50% cash share of total declared dividend. Effective FY 2026 onward, per SPCD Circular No. 06.",
      tone: "warn",
    },
    {
      kind: "comparison",
      before_label: "Capital",
      after_label: "Dividend",
      rows: [
        {
          title: "Healthy but blocked",
          before: "Below 2,000",
          after: "Blocked",
          description: "City, Prime, Jamuna, EBL, Pubali, IFIC, Islami, UCB, Bank Asia, Southeast, Premier — strong banks held below the Tk 2,000 cr line. No cash payout regardless of earnings or solvency.",
          tone: "bear",
        },
        {
          title: "Healthy and eligible",
          before: "Above 2,000",
          after: "Eligible",
          description: "BRAC Bank (Tk 2,290 cr) — only just clears. The lone clean pass on both health and capital size.",
          tone: "bull",
        },
        {
          title: "Weak, rightly limited",
          before: "Below 2,000",
          after: "Blocked",
          description: "Smaller struggling banks — capital-constrained and correctly capped. The only quadrant where the rule does what it should.",
          tone: "neu",
        },
        {
          title: "Weak but cleared",
          before: "Above 2,000",
          after: "Eligible",
          description: "NBL (Tk 3,220 cr paid-up) — Tk 3,200 cr in bad loans, but passes on capital size alone.",
          tone: "bear",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "The rule's perversity is in the ordering. NBL — paid-up Tk 3,220 cr, bad loans Tk 3,200 cr — sits at the top of the eligible list. Eleven listed private-sector banks, several with visibly stronger asset quality, are debarred from cash distribution because their nominal paid-up capital falls below an arbitrary Tk 2,000 cr line. IFIC misses by just Tk 78 cr; Premier by Tk 767 cr.",
        "Section 23 of the Income Tax Act 2023 then closes the trap. Listed companies that pay no cash dividend, or whose stock dividend exceeds cash, face a 10% additional tax. The nine blocked banks must therefore choose between accepting the Section 23 surcharge or violating BB's circular — a choice between two regulators with opposite signals to the same balance sheet.",
      ],
    },
  ],
  banker_read: "Treasury and capital-planning desks at the blocked banks should price two simultaneous hits into FY 2026 board resolutions: forced stock-or-nil dividend declarations and a 10% Section 23 surcharge on whichever the board picks. The least-bad path is usually a no-dividend cycle treated as a regulatory tax, with parallel engagement at SPCD to seek a one-time exemption or to push for the threshold's redesign. For equity research, the affected names should re-rate not on earnings quality but on the regulatory whipsaw — P/B compression is the dominant risk through the disclosure window, and IFIC (Tk 78 cr short) is the cleanest case for a one-time discretionary capital top-up to clear the line. Credit committees should note the perverse direction: a rule sold as depositor-protection clears cash payouts at the listed bank carrying Tk 3,200 cr in bad loans while barring nine of its healthier peers. If BB intends to revisit the design, the cleaner gating axes are capital adequacy ratio plus NPL coverage, not a single nominal paid-up threshold. Until the circular is amended, the listed banking sub-sector trades on regulatory risk, not fundamentals.",
};
