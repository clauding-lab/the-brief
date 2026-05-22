import type { LongViewData } from "@/types/brief";

// The current pinned Long View. Set to `null` when nothing is pinned.
// To change the pin: replace this entire export with new data per the v1.2.0
// block schema, commit, and let the user preview on a Vercel branch deployment
// before merging to main. See docs/longview-workflow.md for the full recipe.

export const longView: LongViewData | null = {
  posted_at: "2026-05-22T00:55:00Z",
  title: "Listed MNCs' Q1 profit slumps 6% on demand and costs",
  lead: "Eleven listed multinational subsidiaries reported a 6% year-on-year drop in aggregate Q1 profit to Tk 12.20bn, against a 4% revenue decline to Tk 103bn. The composition is uneven — four firms grew, four fell, two stayed in the red, one slipped into loss — but the cluster of causes (9% inflation, weak credit growth, slow ADP) is broadly shared.",
  blocks: [
    {
      kind: "stat",
      value: "−6",
      unit: "%",
      label: "AGGREGATE PROFIT · 11 LISTED MNCs · Q1 YoY",
      body: "Tk 12.20bn in aggregate profit against Tk 103bn in revenue (−4% YoY). Four firms grew; four fell; two stayed in the red; one slipped into loss.",
      tone: "bear",
    },
    {
      kind: "comparison",
      before_label: "Q1 2025",
      after_label: "Q1 2026",
      rows: [
        {
          title: "Grameenphone · Revenue (Tk bn)",
          before: "38.3",
          after: "37.6",
          description: "Revenue −2%; cost control lifted profit +4.4%.",
        },
        {
          title: "Robi Axiata · Profit (Tk bn)",
          before: "1.2",
          after: "2.3",
          description: "+86% on stronger data revenue and more 4G users.",
          tone: "bull",
        },
        {
          title: "BAT · Revenue (Tk bn)",
          before: "23.0",
          after: "17.8",
          description: "Revenue −23%; profit fell to Tk 2.1bn (−34%).",
          tone: "bear",
        },
        {
          title: "Singer Bangladesh · Loss (Tk bn)",
          before: "−0.35",
          after: "−0.58",
          description: "Loss widened 66% as finance costs surged.",
          tone: "bear",
        },
        {
          title: "Heidelberg Materials · Profit (Tk bn)",
          before: "0.20",
          after: "−0.05",
          description: "Slipped to a Tk 50m loss from a Tk 197m profit.",
          tone: "bear",
        },
        {
          title: "LafargeHolcim · Profit (Tk bn)",
          before: "1.40",
          after: "1.15",
          description: "−19% amid slower construction activity.",
          tone: "bear",
        },
        {
          title: "Reckitt Benckiser · Profit (Tk bn)",
          before: "0.10",
          after: "0.07",
          description: "−28%.",
          tone: "bear",
        },
        {
          title: "Unilever Consumer Care · Profit (Tk bn)",
          before: "0.14",
          after: "0.12",
          description: "−12%.",
          tone: "bear",
        },
        {
          title: "Linde Bangladesh · Profit (Tk bn)",
          before: "0.26",
          after: "0.36",
          description: "+36% YoY.",
          tone: "bull",
        },
        {
          title: "Bata · Profit (Tk bn)",
          before: "0.30",
          after: "0.31",
          description: "Marginal growth on Eid-season sales.",
        },
        {
          title: "RAK Ceramics · Loss (Tk bn)",
          before: "−0.09",
          after: "−0.10",
          description: "Remained in loss; loss increased.",
          tone: "bear",
        },
      ],
    },
    {
      kind: "bullet-list",
      eyebrow: "WHY EARNINGS WEAKENED",
      items: [
        { text: "**Inflation hovered around 9%**, squeezing household spending and discretionary baskets.", tone: "warn" },
        { text: "**Higher raw material, fuel and energy costs** compressed gross margins across cement, FMCG, and consumer durables.", tone: "warn" },
        { text: "**Geopolitical tensions disrupted global supply chains**, lengthening import lead times and lifting landed input costs.", tone: "warn" },
        { text: "**Private-sector credit growth stayed weak at around 6%**, restraining working-capital expansion and capex." },
        { text: "**Slower ADP and infrastructure spending hurt cement demand**, hitting LafargeHolcim and Heidelberg directly." },
        { text: "**Weak consumer confidence limited companies' ability to pass on costs**, especially in FMCG and consumer durables." },
      ],
    },
  ],
  banker_read: "This is a sector-rotation read more than an aggregate-demand call. Telecom (Grameenphone, Robi) and industrial gases (Linde) shrugged off the macro; cement, FMCG, and consumer durables bore the brunt. For credit teams: the names with widening losses or profit-to-loss flips — Singer, Heidelberg, RAK — are where covenant headroom is thinnest, and the finance-cost line is the leading indicator to monitor. For equity research: BAT's −34% profit drop on −23% revenue is the volume-not-price story finally landing, while the four MNCs that grew reveal pricing power and category positioning, not luck. Treasury desks should expect more frequent corporate refinancing requests; with private-sector credit growth stuck near 6%, banks are increasingly funding sovereign paper instead of corporate term loans — which is the diagnosis, not the prescription.",
};
