import { describe, expect, it } from "vitest";
import type { ChartConfiguration, TooltipItem, TooltipModel } from "chart.js";
import { __internals, chartConfigs, type SeriesByKey } from "./chartConfigs";

type Point = { x: string; y: number | null };
function points(config: ChartConfiguration<"line">, dataset: number): Point[] {
  return config.data.datasets[dataset].data as unknown as Point[];
}
function label(config: ChartConfiguration<"line">, datasetIndex: number, dataIndex: number) {
  const dataset = config.data.datasets[datasetIndex];
  const raw = points(config, datasetIndex)[dataIndex];
  const callback = config.options!.plugins!.tooltip!.callbacks!.label!;
  return callback.call({} as TooltipModel<"line">, {
    dataset, datasetIndex, dataIndex, raw, parsed: { x: Date.parse(raw.x), y: raw.y },
  } as TooltipItem<"line">);
}
const APR = "2026-04-30", MAY = "2026-05-31", JUN = "2026-06-30";
const FX: SeriesByKey = {
  exports_usd_mn_monthly: [[JUN, 4202.69], [APR, 4000], [MAY, 4402.78]],
  remittance_usd_mn_monthly: [[MAY, 3442.58], [JUN, 2820]],
  imports_usd_mn_monthly: [[MAY, 6108.22], [APR, 6000]],
};

describe("alignSeriesByDate", () => {
  it("sorts the date union, pads starts/interior gaps, preserves nulls and never mutates inputs", () => {
    const input: SeriesByKey = { a: [[JUN, 3], [APR, 1]], b: [[MAY, null], [JUN, 2]], c: [] };
    const before = structuredClone(input);
    expect(__internals.alignSeriesByDate(input)).toEqual({
      a: [[APR, 1], [MAY, null], [JUN, 3]],
      b: [[APR, null], [MAY, null], [JUN, 2]],
      c: [[APR, null], [MAY, null], [JUN, null]],
    });
    expect(input).toEqual(before);
  });
  it("coalesces identical duplicates and makes conflicting duplicates unavailable regardless of order", () => {
    for (const values of [[4, 5, 4], [5, 4, 4], [4, null], [null, 4]]) {
      expect(__internals.alignSeriesByDate({ a: values.map(v => [MAY, v]) })).toEqual({ a: [[MAY, null]] });
    }
    expect(__internals.alignSeriesByDate({ a: [[MAY, 4], [MAY, 4]], b: [[MAY, null], [MAY, null]] }))
      .toEqual({ a: [[MAY, 4]], b: [[MAY, null]] });
  });
  it("handles an empty input", () => expect(__internals.alignSeriesByDate({})).toEqual({}));
});

describe("FX generated geometry and real tooltip callback", () => {
  it("shows May remittance 3.44258 and imports 6.10822, never the cumulative or negative geometry", () => {
    const config = chartConfigs.fxBalance({ series: FX, reducedMotion: true });
    expect(points(config, 1)[1].x).toBe(MAY);
    expect(points(config, 1)[1].y).toBeCloseTo(7.84536);
    expect(points(config, 2)[1].y).toBeCloseTo(-6.10822);
    expect(points(config, 3)[1].y).toBeCloseTo(1.73714);
    expect(label(config, 1, 1)).toBe("Remittance: $3.44258bn");
    expect(label(config, 2, 1)).toBe("Imports: $6.10822bn");
    expect(label(config, 3, 1)).toBe("Net basic balance: $1.73714bn");
    expect(config.data.datasets[1].fill).toBe("-1");
    expect(config.data.datasets[3].fill).toBe(false);
    expect(config.options!.scales!.y!.stacked).not.toBe(true);
    expect(config.options!.animation).toBe(false);
  });
  it("uses missing components as null in totals and aligns all dates including import-only periods", () => {
    const config = chartConfigs.fxBalance({ series: { ...FX, imports_usd_mn_monthly: [["2026-03-31", 5000], ...FX.imports_usd_mn_monthly] } });
    for (let i = 0; i < 4; i++) expect(points(config, i).map(p => p.x)).toEqual(["2026-03-31", APR, MAY, JUN]);
    expect(points(config, 1).map(p => p.y)).toEqual([null, null, expect.closeTo(7.84536), expect.closeTo(7.02269)]);
    expect(points(config, 3).map(p => p.y)).toEqual([null, null, expect.closeTo(1.73714), null]);
  });
  it("does not choose a conflicting duplicate by input order or fabricate a net", () => {
    const config = chartConfigs.fxBalance({ series: { ...FX, remittance_usd_mn_monthly: [[MAY, 3442.58], [MAY, 9999]] } });
    expect(points(config, 1)[1].y).toBeNull();
    expect(points(config, 3)[1].y).toBeNull();
    expect(label(config, 1, 1)).toBe("Remittance: —");
  });
});

describe("multi-series index tooltips", () => {
  it("pairs May food 9.06 with May headline despite different starts and an interior gap", () => {
    const config = chartConfigs.cpiTrend({ series: {
      cpi_12m_avg_monthly: [[JUN, 8.2], [APR, 8.8], [MAY, 8.6]],
      cpi_p2p_food_monthly: [[MAY, 9.06], [JUN, 8.8]],
      cpi_p2p_nonfood_monthly: [[APR, 8], [JUN, null]],
    } });
    for (let i = 0; i < 3; i++) expect(points(config, i).map(p => p.x)).toEqual([APR, MAY, JUN]);
    expect(label(config, 1, 1)).toBe("Food (P-to-P): 9.06%");
    expect(label(config, 2, 1)).toBe("Non-Food (P-to-P): —");
  });
  it.each([
    ["reserves", "gross_reserves_usd_bn_monthly", "net_reserves_bpm6_usd_bn_monthly"],
    ["moneyMarket", "dommr", "bofr"],
    ["fxFlows", "monthly_export", "monthly_remittance"],
  ] as const)("aligns %s to dates instead of mismatched positions", (builder, a, b) => {
    const config = chartConfigs[builder]({ series: { [a]: [[JUN, 3], [APR, 1]], [b]: [[MAY, 2]] } });
    expect(config.data.datasets[0].data).toEqual([{ x: APR, y: 1 }, { x: MAY, y: null }, { x: JUN, y: 3 }]);
    expect(config.data.datasets[1].data).toEqual([{ x: APR, y: null }, { x: MAY, y: 2 }, { x: JUN, y: null }]);
  });
});
