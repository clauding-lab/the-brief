// R2 fix 16: the pipeline stamps a card's change figures with the source's full
// decimals (e.g. "−10.17525", "−0.183321467065674%"); the snapshot strip must
// cut them for the screen exactly as it cuts the card value (cleanMetricValue),
// never show the raw tail.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Section } from "@/types/brief";
import { SnapshotStrip } from "./SnapshotStrip";

function dseSection(delta?: string, deltaPct?: string): Section {
  return {
    slug: "dse",
    metrics: [{ label: "DSEX close", value: "5,540.32037", delta, delta_pct: deltaPct }],
  } as unknown as Section;
}

describe("SnapshotStrip — change figures", () => {
  it("cuts the stamped change figures like the card value", () => {
    const html = renderToStaticMarkup(
      <SnapshotStrip sections={[dseSection("−10.17525", "−0.183321467065674%")]} />,
    );
    expect(html).toContain("5,540.32<");
    expect(html).toContain(">−10.17<");
    expect(html).toContain(">−0.18%<");
    expect(html).not.toContain("10.17525");
    expect(html).not.toContain("0.183321467065674");
  });

  it("shows no change line when the pipeline cleared the change figures", () => {
    const html = renderToStaticMarkup(<SnapshotStrip sections={[dseSection()]} />);
    expect(html).not.toContain("tb-delta");
  });
});
