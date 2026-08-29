// Fixtures below are the real production values from issue #211 (brief_date
// 2026-08-29), pulled live via the REST endpoint — every metric row whose
// `value` carried 3+ decimal places, plus the values on the same issue that
// were already fine and must survive the cut untouched.
import { describe, expect, it } from "vitest";
import { cleanMetricValue } from "./format";

describe("cleanMetricValue — repeated $ collapse", () => {
  it("collapses a run of $ to one", () => {
    expect(cleanMetricValue("$$108.17")).toBe("$108.17");
    expect(cleanMetricValue("$$$4.20")).toBe("$4.20");
  });

  it("leaves a single $ alone", () => {
    expect(cleanMetricValue("$108.17")).toBe("$108.17");
  });

  it("returns an empty string for null/undefined/empty", () => {
    expect(cleanMetricValue(null)).toBe("");
    expect(cleanMetricValue(undefined)).toBe("");
    expect(cleanMetricValue("")).toBe("");
  });
});

describe("cleanMetricValue — decimal cut (issue #211 live values)", () => {
  // [stored value, what the reader must see]
  const CASES: ReadonlyArray<[string, string]> = [
    ["36.4222", "36.42"], // bb / fx — Gross Reserves
    ["122.9959", "122.99"], // fx — USD/BDT mid (the owner-named case)
    ["4512.100098", "4512.10"], // fx — Gold
    ["5655.68313", "5655.68"], // dse — DSEX close
    ["0.2765", "0.27"], // dse — DSEX %Δ
    ["467.0148", "467.01"], // dse — Turnover
    ["8.829", "8.82"], // tbond — 91d T-Bill cut-off
    ["9.234", "9.23"], // tbond — 10y Govt Bond
    ["4.848200071", "4.84"], // macro — Import Cover
    ["88.01000214", "88.01"], // iran — Brent spot
    ["83.30000305", "83.30"], // iran — WTI spot
  ];

  it.each(CASES)("cuts %s to %s", (raw, want) => {
    expect(cleanMetricValue(raw)).toBe(want);
  });

  it("truncates rather than rounds", () => {
    // The 3 live values where the two conventions disagree. Owner decision
    // 2026-08-29: shown "122.9959", he asked for "122.99".
    expect(cleanMetricValue("122.9959")).toBe("122.99"); // not 123.00
    expect(cleanMetricValue("8.829")).toBe("8.82"); // not 8.83
    expect(cleanMetricValue("4.848200071")).toBe("4.84"); // not 4.85
  });

  it("keeps a trailing zero it did not add", () => {
    expect(cleanMetricValue("83.30000305")).toBe("83.30");
    expect(cleanMetricValue("4512.100098")).toBe("4512.10");
  });

  it("does not go through float arithmetic", () => {
    // 8.829 * 100 === 882.9000000000001 in IEEE-754; a Math.trunc(n * 100)
    // implementation is fine here but wrong for a value stored with error
    // in the other direction, which is exactly the population being cleaned.
    expect(cleanMetricValue("8.8299999999")).toBe("8.82");
    expect(cleanMetricValue("2.9700000000000002")).toBe("2.97");
  });
});

describe("cleanMetricValue — values that must pass through untouched", () => {
  // Real issue #211 values already at <= 2dp. This function CUTS, never pads.
  const UNTOUCHED = [
    "9.5",
    "7.5",
    "11",
    "9.18",
    "32.26",
    "1.56",
    "4.2",
    "-3.31",
    "185",
    "144",
    "2858.68",
    "0",
    "0.00",
  ];

  it.each(UNTOUCHED)("leaves %s alone", (v) => {
    expect(cleanMetricValue(v)).toBe(v);
  });

  it("leaves compound and non-numeric strings alone", () => {
    expect(cleanMetricValue("3.500-4.000")).toBe("3.500-4.000");
    expect(cleanMetricValue("2026.08.29")).toBe("2026.08.29");
    expect(cleanMetricValue("n/a")).toBe("n/a");
    expect(cleanMetricValue("—")).toBe("—");
  });

  it("never collapses a small non-zero value to 0.00", () => {
    expect(cleanMetricValue("0.0004")).toBe("0.0004");
    expect(cleanMetricValue("-0.0004")).toBe("-0.0004");
  });
});

describe("cleanMetricValue — decorated numbers", () => {
  it("cuts inside a currency prefix and a unit suffix", () => {
    expect(cleanMetricValue("$88.01000214")).toBe("$88.01");
    expect(cleanMetricValue("8.829%")).toBe("8.82%");
    expect(cleanMetricValue("36.4222bn")).toBe("36.42bn");
  });

  it("handles a negative and a thousands-separated value", () => {
    expect(cleanMetricValue("-3.3145")).toBe("-3.31");
    expect(cleanMetricValue("5,655.68313")).toBe("5,655.68");
  });
});
