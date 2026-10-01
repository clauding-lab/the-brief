// R3c: a chartless section's chart arrays. The R3 test database's
// get_latest_brief returns `series: []` / `notes: []` for a section with no
// chart points (COALESCE in its SQL; raw JSON kept in R/fixR3c-latest-chartless.json),
// but a reader that returns `null` instead must not crash the page: the SPA
// treats a null chart array exactly like an empty one. Rows are SYNTHETIC.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Section as SectionType } from "@/types/brief";
import { Section } from "./Section";

function chartless(freshness: SectionType["freshness"], chart: readonly [] | null): SectionType {
  return {
    slug: "headlines",
    ord: 1,
    title: "Headlines",
    group_key: "overview",
    freshness,
    metrics: [],
    news: [{ headline: "SYNTHETIC headline", source: "SYNTHETIC" }],
    series: chart,
    notes: chart,
  } as unknown as SectionType;
}

describe("Section — chartless sections render the same for [] and null chart arrays", () => {
  for (const chart of [[], null] as const) {
    const label = chart === null ? "null" : "[]";

    it(`collapses an unavailable section with ${label} series to the no-data note`, () => {
      const html = renderToStaticMarkup(
        <Section section={chartless("unavailable", chart)} diffMode={false} />,
      );
      expect(html).toContain("No fresh data this issue");
    });

    it(`renders a fresh chartless section with ${label} series without a chart`, () => {
      const html = renderToStaticMarkup(<Section section={chartless("fresh", chart)} diffMode={false} />);
      expect(html).toContain("SYNTHETIC headline");
      expect(html).not.toContain("<canvas");
    });
  }

  it("renders identical markup for [] and null chart arrays", () => {
    for (const freshness of ["unavailable", "fresh"] as const) {
      const empty = renderToStaticMarkup(<Section section={chartless(freshness, [])} diffMode={false} />);
      const nulls = renderToStaticMarkup(<Section section={chartless(freshness, null)} diffMode={false} />);
      expect(nulls).toBe(empty);
    }
  });
});
