// Fixtures below are real production values (issue #204, brief_date
// 2026-08-22, pulled live via the anon REST endpoint — not idealized
// numbers) so the threshold sweep exercises the actual mixed month-start /
// month-end stamping the normalization is meant to survive.
import { describe, expect, it } from "vitest";
import {
  getChartAuctionNote,
  getChartLatestCaption,
  getPerSeriesStaleness,
  YIELD_LADDER_AUCTION_NOTE_KEY,
  __internals,
} from "./chartMeta";
import { SECTION_TO_CHART } from "./chartConfigs";
import type { Section, SeriesPoint } from "@/types/brief";

const { periodEnd, num2, CHART_SPECS } = __internals;

function makeSection(series: SeriesPoint[]): Section {
  return {
    slug: "test",
    ord: 1,
    title: "Test Section",
    group_key: "overview",
    metrics: [],
    news: [],
    series,
    notes: [],
  };
}

const ISSUE_DATE = "2026-08-22";

describe("periodEnd", () => {
  it("normalizes a month-START stamp to that month's last day", () => {
    expect(periodEnd("2026-07-01", "monthly")).toBe("2026-07-31");
  });

  it("leaves an already month-END stamp unchanged", () => {
    expect(periodEnd("2026-07-31", "monthly")).toBe("2026-07-31");
  });

  it("handles a non-leap February correctly (2026)", () => {
    expect(periodEnd("2026-02-01", "monthly")).toBe("2026-02-28");
  });

  it("handles a leap February correctly (2024)", () => {
    expect(periodEnd("2024-02-01", "monthly")).toBe("2024-02-29");
  });

  it("does not touch a daily-cadence date", () => {
    expect(periodEnd("2026-08-20", "daily")).toBe("2026-08-20");
  });

  it("treats a month-start and a month-end stamp for the SAME period as equally fresh", () => {
    // This is the bug being fixed: without normalization, "2026-07-01"
    // reads ~30 days older than "2026-07-31" even though both describe
    // July's data.
    expect(periodEnd("2026-07-01", "monthly")).toBe(periodEnd("2026-07-31", "monthly"));
  });
});

describe("num2", () => {
  it("never drops a trailing zero", () => {
    expect(num2(36.4)).toBe("36.40");
  });

  it("keeps two decimals when already present", () => {
    expect(num2(36.42)).toBe("36.42");
  });

  it("pads a whole number to two decimals", () => {
    expect(num2(0)).toBe("0.00");
  });
});

describe("getChartLatestCaption", () => {
  it("binds to the chart's OWN series, not an unrelated metric (regression: the bb/Overnight Call Money bug)", () => {
    const section = makeSection([
      { key: "gross_reserves_usd_bn_monthly", ts: "2026-06-30", value: 34.5478 },
      { key: "gross_reserves_usd_bn_monthly", ts: "2026-07-31", value: 36.4222 },
      { key: "net_reserves_bpm6_usd_bn_monthly", ts: "2026-07-31", value: 31.6012 },
    ]);
    const latest = getChartLatestCaption(section, "reserves");
    expect(latest).not.toBeNull();
    expect(latest!.label).toBe("Gross reserves");
    expect(latest!.value).toBe("$36.42bn");
    expect(latest!.periodLabel).toBe("Jul 2026");
  });

  it("falls back to the single most recent point across all series when no spec exists for the configKey", () => {
    const section = makeSection([
      { key: "some_future_series", ts: "2026-01-01", value: 1 },
      { key: "some_future_series", ts: "2026-05-01", value: 2 },
    ]);
    const latest = getChartLatestCaption(section, null);
    expect(latest).not.toBeNull();
    expect(latest!.ts).toBe("2026-05-01");
  });
});

describe("getPerSeriesStaleness — threshold sweep against live #204 data", () => {
  it("reserves: neither gross nor net reserves is stale at the issue date (22d < 45d)", () => {
    const section = makeSection([
      { key: "gross_reserves_usd_bn_monthly", ts: "2026-07-31", value: 36.4222 },
      { key: "net_reserves_bpm6_usd_bn_monthly", ts: "2026-07-31", value: 31.6012 },
    ]);
    const result = getPerSeriesStaleness(section, "reserves", ISSUE_DATE);
    expect(result.every((s) => !s.isStale)).toBe(true);
  });

  it("fx: imports (period-end Mar 2026, 144d) and exports (period-end Jun 2026, 53d) flag stale; remittance (22d) does not", () => {
    const section = makeSection([
      { key: "exports_usd_mn_monthly", ts: "2026-06-01", value: 4030 },
      { key: "imports_usd_mn_monthly", ts: "2026-03-01", value: 5500 },
      { key: "remittance_usd_mn_monthly", ts: "2026-07-01", value: 2820 },
    ]);
    const result = getPerSeriesStaleness(section, "fxBalance", ISSUE_DATE);
    const byKey = Object.fromEntries(result.map((s) => [s.key, s]));
    expect(byKey["exports_usd_mn_monthly"].isStale).toBe(true);
    expect(byKey["imports_usd_mn_monthly"].isStale).toBe(true);
    expect(byKey["imports_usd_mn_monthly"].noteLabel).toBe("IMPORTS ENDS MAR 2026");
    expect(byKey["remittance_usd_mn_monthly"].isStale).toBe(false);
  });

  it("macro/CPI: headline CPI (period-end Jun 2026, 53d) is stale", () => {
    const section = makeSection([
      { key: "cpi_12m_avg_monthly", ts: "2026-06-01", value: 8.5 },
      { key: "cpi_p2p_food_monthly", ts: "2026-06-01", value: 7.9 },
      { key: "cpi_p2p_nonfood_monthly", ts: "2026-06-01", value: 9.1 },
    ]);
    const result = getPerSeriesStaleness(section, "cpiTrend", ISSUE_DATE);
    expect(result.every((s) => s.isStale)).toBe(true);
  });

  it("fiscal/NBR: a 2025-10-31 print (295d) is stale", () => {
    const section = makeSection([{ key: "nbr_revenue_monthly_cr", ts: "2025-10-31", value: 21000 }]);
    const result = getPerSeriesStaleness(section, "fiscalNbr", ISSUE_DATE);
    expect(result[0].isStale).toBe(true);
  });

  it("tbond/yieldLadder: a Jul 2026 10Y print (22d) is NOT stale", () => {
    const section = makeSection([{ key: "yield_10y_monthly", ts: "2026-07-01", value: 8.42 }]);
    const result = getPerSeriesStaleness(section, "yieldLadder", ISSUE_DATE);
    const tenY = result.find((s) => s.key === "yield_10y_monthly");
    expect(tenY?.isStale).toBe(false);
  });

  it("dsex: a 2-trading-day-old close is NOT stale", () => {
    const section = makeSection([{ key: "dsex", ts: "2026-08-20", value: 5219.74 }]);
    const result = getPerSeriesStaleness(section, "dsex", ISSUE_DATE);
    expect(result[0].isStale).toBe(false);
  });

  it("remit/tbond do not false-fire at +4 days past the issue date (still inside cadence-normal reporting lag)", () => {
    const remitSection = makeSection([
      { key: "remittance_usd_mn_monthly", ts: "2026-07-01", value: 2820 },
    ]);
    const tbondSection = makeSection([{ key: "yield_10y_monthly", ts: "2026-07-01", value: 8.42 }]);
    expect(getPerSeriesStaleness(remitSection, "remitFlow", "2026-08-26")[0].isStale).toBe(false);
    expect(
      getPerSeriesStaleness(tbondSection, "yieldLadder", "2026-08-26").find(
        (s) => s.key === "yield_10y_monthly"
      )?.isStale
    ).toBe(false);
  });

  it("remit/tbond STILL do not false-fire at +14 days (36d < 45d threshold)", () => {
    const remitSection = makeSection([
      { key: "remittance_usd_mn_monthly", ts: "2026-07-01", value: 2820 },
    ]);
    const tbondSection = makeSection([{ key: "yield_10y_monthly", ts: "2026-07-01", value: 8.42 }]);
    expect(getPerSeriesStaleness(remitSection, "remitFlow", "2026-09-05")[0].isStale).toBe(false);
    expect(
      getPerSeriesStaleness(tbondSection, "yieldLadder", "2026-09-05").find(
        (s) => s.key === "yield_10y_monthly"
      )?.isStale
    ).toBe(false);
  });

  it("dsex DOES correctly flip stale at +14 days (16d > 7d) — a genuine gap, not a false fire", () => {
    const section = makeSection([{ key: "dsex", ts: "2026-08-20", value: 5219.74 }]);
    const result = getPerSeriesStaleness(section, "dsex", "2026-09-05");
    expect(result[0].isStale).toBe(true);
  });
});

describe("SECTION_TO_CHART ↔ CHART_SPECS parity", () => {
  // The only guard on the four-way series-key coupling ('dommr'/'bofr'-style
  // strings repeated across chart_series_fetcher.py metric ids, chartConfigs
  // builder keys, CHART_SPECS series[].key, and CHART_SPECS primaryKey):
  // every chart a section can render must have a spec here, and that spec's
  // primaryKey must be one of its own plotted series keys — otherwise the
  // "LATEST PLOTTED" caption silently falls back and per-series staleness
  // goes blind for that chart.
  //
  // `lng` (mapped from the retired `comm` commodities section, AGENTS.md
  // landmine 30) is the one documented exception: chartMeta.ts deliberately
  // carries no lng spec, and removing the dead SECTION_TO_CHART row belongs
  // to a chartConfigs.ts cleanup pass, not this test.
  const RETIRED_CHART_KEYS = new Set<string>(["lng"]);

  it("every live SECTION_TO_CHART key has a CHART_SPECS entry whose primaryKey is in its own series list", () => {
    const liveKeys = Object.values(SECTION_TO_CHART).filter(
      (key): key is NonNullable<typeof key> => key != null && !RETIRED_CHART_KEYS.has(key),
    );
    expect(liveKeys.length).toBeGreaterThan(0);
    for (const key of liveKeys) {
      const spec = CHART_SPECS[key];
      expect(spec, `CHART_SPECS has no entry for chart key "${key}"`).toBeDefined();
      const seriesKeys = spec!.series.map((s) => s.key);
      expect(
        seriesKeys,
        `CHART_SPECS["${key}"].primaryKey "${spec!.primaryKey}" is not one of its own series keys`,
      ).toContain(spec!.primaryKey);
    }
  });
});

describe("getChartAuctionNote — §tbond bottom footnote", () => {
  function withNotes(notes: Section["notes"]): Section {
    return { ...makeSection([]), notes };
  }

  it("renders the last auction date the newest curve is built from", () => {
    const s = withNotes([
      { series_key: YIELD_LADDER_AUCTION_NOTE_KEY, ts: "2026-08-27", label: "last auction" },
    ]);
    expect(getChartAuctionNote(s)).toBe("Curve built from auctions through 27 Aug 2026");
  });

  it("does not pad the day — '5 Aug', not '05 Aug'", () => {
    const s = withNotes([
      { series_key: YIELD_LADDER_AUCTION_NOTE_KEY, ts: "2026-08-05", label: "last auction" },
    ]);
    expect(getChartAuctionNote(s)).toBe("Curve built from auctions through 5 Aug 2026");
  });

  it("returns null when the pipeline attached no such note", () => {
    expect(getChartAuctionNote(makeSection([]))).toBeNull();
  });

  it("ignores notes belonging to other series (e.g. DSEX event markers)", () => {
    const s = withNotes([{ series_key: "dsex", ts: "2026-08-27", label: "budget" }]);
    expect(getChartAuctionNote(s)).toBeNull();
  });

  it("returns null on an unparseable ts rather than echoing raw text", () => {
    const s = withNotes([
      { series_key: YIELD_LADDER_AUCTION_NOTE_KEY, ts: "sometime in August", label: "x" },
    ]);
    expect(getChartAuctionNote(s)).toBeNull();
  });
});
