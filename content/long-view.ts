import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-24T04:42:00Z",
  title: "BB picked the wrong ruler for bank cash dividends",
  lead: "BB SPCD Circular No. 06 (23 May 2026) ties any cash-dividend eligibility to Tk 2,000 cr in paid-up capital, blocking City, Prime, Jamuna, EBL, and Pubali while clearing National Bank past Tk 3,200 cr in bad loans. Section 23 of the Income Tax Act 2023 then layers a 10% additional tax on listed companies that fail to pay cash or whose stock dividend exceeds cash — leaving the blocked banks trapped between two regulators.",
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
      kind: "bullet-list",
      eyebrow: "FOUR QUADRANTS — TWO MISALIGNMENTS",
      items: [
        {
          text: "**Healthy but blocked.** City, Prime, Jamuna, EBL, Pubali, and others — strong banks held below the Tk 2,000 cr line. No cash payout permitted regardless of earnings or solvency.",
          tone: "bear",
        },
        {
          text: "**Healthy and eligible.** BRAC Bank — only just clears the threshold. The lone clean pass on both health and capital size.",
          tone: "bull",
        },
        {
          text: "**Weak but clears the bar.** National Bank — Tk 3,200 cr in bad loans, but passes the rule on capital size alone.",
          tone: "bear",
        },
        {
          text: "**Weak, rightly limited.** Struggling small banks — capital-constrained and correctly capped. The only quadrant where the rule does what it should.",
          tone: "neu",
        },
      ],
    },
    {
      kind: "prose",
      paragraphs: [
        "Section 23 of the Income Tax Act 2023 layers a 10% additional tax on listed companies that fail to pay cash dividends, or whose stock dividend exceeds cash. The healthy-but-blocked banks face a vise: BB blocks the cash payout, NBR taxes the absence. The same depositor-protection logic that justifies the paid-up floor punishes the listed shareholders who funded the equity in the first place.",
        "The deeper failure is the ruler. Paid-up capital is a nominal measure; bank health rides on capital adequacy ratio, NPL coverage, and loss-absorption buffers. By gating cash dividends on a single nominal threshold, BB has produced a rule that permits cash payouts at banks carrying Tk 3,200 cr in bad loans while debarring banks that are visibly more solvent. The deposit base the rule was written to protect is now exposed at the wrong door.",
      ],
    },
  ],
  banker_read: "Treasury and capital-planning desks at City, Prime, Jamuna, EBL, and Pubali should price two simultaneous hits into FY 2026 board resolutions: blocked cash distributions and a 10% Section 23 surcharge on the resulting stock-heavy or no-dividend declarations. The least-bad path may be a no-dividend cycle treated as a regulatory tax, with parallel lobbying for a one-time BB exemption or rule revision. For equity research, the affected names should re-rate not on earnings quality but on the regulatory whipsaw — P/B compression is the dominant risk through the disclosure window. Credit committees should note the perverse direction: a rule sold as depositor-protection clears cash payouts at the bank with Tk 3,200 cr in bad loans while barring its healthier peers. If BB intends to revisit the design, the cleaner gating axes are capital adequacy ratio plus NPL coverage, not a single nominal paid-up threshold. Until the circular is amended, the listed banking sub-sector trades on regulatory risk, not fundamentals.",
};
