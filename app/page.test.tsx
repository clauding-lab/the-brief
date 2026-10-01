// R3d (design test 8): the home page never renders an empty or half edition.
// When there is no published edition, or the read fails, the server render
// falls back to the static issue in lib/staticFallback.ts. The "nothing
// published" body below is exactly what get_latest_brief returned on the R3
// test database with every edition set to draft (R3d evidence fixR3d-v2-latest-no-published.json);
// the live body is SYNTHETIC.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import type { BriefPayload } from "@/types/brief";
import { STATIC_FALLBACK } from "@/lib/staticFallback";

const rpc = vi.fn();
vi.mock("@supabase/supabase-js", () => ({ createClient: vi.fn(() => ({ rpc })) }));
vi.mock("./components/ClientApp", () => ({ ClientApp: () => null }));

import Home from "./page";

const NOTHING_PUBLISHED = { brief: null, sections: [] };

async function initialData(): Promise<BriefPayload & { _source?: string }> {
  const element = (await Home()) as ReactElement<{ initialData: BriefPayload & { _source?: string } }>;
  return element.props.initialData;
}

describe("home page — static fallback when no complete published edition can be read", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://synthetic.invalid");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "synthetic-anon-key");
    rpc.mockReset();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("serves the static issue when the database has no published edition (drafts stay hidden)", async () => {
    rpc.mockResolvedValue({ data: NOTHING_PUBLISHED, error: null });
    expect(await initialData()).toBe(STATIC_FALLBACK);
    expect(rpc).toHaveBeenCalledWith("get_latest_brief");
  });

  it("serves the static issue when the latest-edition read fails", async () => {
    rpc.mockResolvedValue({ data: null, error: { message: "canceling statement due to statement timeout" } });
    expect(await initialData()).toBe(STATIC_FALLBACK);
  });

  it("never serves a body from a read that reported an error", async () => {
    const body = { brief: { ...STATIC_FALLBACK.brief, issue_no: 236 }, sections: STATIC_FALLBACK.sections };
    rpc.mockResolvedValue({ data: body, error: { message: "canceling statement due to statement timeout" } });
    expect(await initialData()).toBe(STATIC_FALLBACK);
  });

  it("serves the static issue when the site is not configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    expect(await initialData()).toBe(STATIC_FALLBACK);
    expect(rpc).not.toHaveBeenCalled();
  });

  it("serves the live edition, marked live, when one is published", async () => {
    const live = { brief: { ...STATIC_FALLBACK.brief, issue_no: 236 }, sections: STATIC_FALLBACK.sections };
    rpc.mockResolvedValue({ data: live, error: null });
    const data = await initialData();
    expect(data).not.toBe(STATIC_FALLBACK);
    expect(data.brief.issue_no).toBe(236);
    expect(data._source).toBe("live");
  });
});
