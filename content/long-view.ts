import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-19T01:27:00Z",
  title: "Mapping the six expenditures behind rising treasury yields",
  lead: "Bangladesh's treasury yields have crossed 11% again, and the supply-side story is the new government's expenditure profile — six concurrent programs adding fresh demand to the bond market without matching revenue. Some are sized; some, like bank recapitalisation, are still 'tens of thousands of crore' away from quantification, leaving the bond market to price the uncertainty.",
  blocks: [
    {
      kind: "bullet-list",
      eyebrow: "BD GOVERNMENT · MAJOR EXPENDITURE PROGRAMMES",
      items: [
        {
          text: "**Family Card · BDT 133,616 cr (5-yr plan).** Pure transfer to 16m+ beneficiaries; rapid scale-up underway. The single largest fiscal expansion in the set, with no revenue offset on the other side.",
        },
        {
          text: "**Power & energy subsidies · BDT 37,000–55,600 cr per year.** The \"hidden deficit,\" BPDB losses included. Politically irreducible; suppresses headline inflation short-term while structurally feeding borrowing needs.",
        },
        {
          text: "**Farmer Card + agri support · BDT 7,000 cr initial + multi-year scaling.** Pilot launched. Blurs the subsidy-versus-productivity policy line; cash and credit arrive before any output gains.",
        },
        {
          text: "**Bank recapitalisation · tens of thousands of crore (not yet disclosed).** Problem acknowledged; recap plan pending. The \"unknown mega liability\" — if government-funded, immediate pressure on bond supply and yields.",
        },
        {
          text: "**Education expansion to 5% of GDP (recurring, not fully costed).** Policy announced; partial rollout under way. Near-term it is a wage + subsidy bill, not revenue. The long-term human-capital case is real but pays out beyond the current curve.",
        },
        {
          text: "**Health expansion to 5% of GDP · 100,000 workers (recurring, not yet quantified).** Recruitment and system expansion planned. A permanent expenditure step-up that raises the structural deficit unless the tax base expands materially.",
        },
      ],
    },
  ],
  banker_read: "Two of these six aren't sized yet — bank recapitalisation and health expansion — and that is where the yield pressure converges. Treasury desks should expect heavy primary supply through any quarter when the recap-plan disclosure lands; positioning the curve as if those tens-of-thousands-of-crore live in 91-day and 182-day issuance is the conservative read. For credit teams: a deficit financed mainly through banking-system absorption crowds out term lending to private corporates — your relationship borrowers are competing with sovereign paper for the same capital, at sovereign rates plus credit spread. That is a tighter origination environment than the headline ADR caps suggest.",
};
