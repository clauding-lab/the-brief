import { beforeEach, describe, expect, it, vi } from "vitest";

// Records every .eq(...) call per table so tests can pin the RLS-posture
// filter (MED-7: draft-hiding rests ENTIRELY on this filter, not on a
// database-side RLS policy — nothing else guards it) without depending on
// a real Supabase project.
const recordedCalls: Record<string, Array<{ method: string; args: unknown[] }>> = {
  briefs: [],
  sections: [],
};

// Test-controlled response per table — set inside each `it` before calling
// the function under test.
const tableResults: Record<string, { data: unknown; error: unknown }> = {
  briefs: { data: [], error: null },
  sections: { data: [], error: null },
};

function makeChain(table: string) {
  const chain: {
    select: ReturnType<typeof vi.fn>;
    eq: ReturnType<typeof vi.fn>;
    order: ReturnType<typeof vi.fn>;
    limit: ReturnType<typeof vi.fn>;
    then: (
      resolve: (value: { data: unknown; error: unknown }) => unknown,
      reject?: (reason: unknown) => unknown
    ) => Promise<unknown>;
  } = {
    select: vi.fn((...args: unknown[]) => {
      recordedCalls[table].push({ method: "select", args });
      return chain;
    }),
    eq: vi.fn((...args: unknown[]) => {
      recordedCalls[table].push({ method: "eq", args });
      return chain;
    }),
    order: vi.fn((...args: unknown[]) => {
      recordedCalls[table].push({ method: "order", args });
      return chain;
    }),
    limit: vi.fn((...args: unknown[]) => {
      recordedCalls[table].push({ method: "limit", args });
      return chain;
    }),
    then: (resolve, reject) => Promise.resolve(tableResults[table]).then(resolve, reject),
  };
  return chain;
}

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    from: vi.fn((table: string) => makeChain(table)),
  })),
}));

// Imported AFTER the mock is registered (vi.mock is hoisted by Vitest, so
// this ordering is safe regardless of where the import statement sits).
import { fetchBriefByIssueNo, __internals } from "./fetchBriefByIssue";

beforeEach(() => {
  recordedCalls.briefs = [];
  recordedCalls.sections = [];
  tableResults.briefs = { data: [], error: null };
  tableResults.sections = { data: [], error: null };
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test-anon-key");
});

describe("fetchBriefByIssueNo — landmine 33 (same-day republish race)", () => {
  it("returns null when the briefs row exists but has zero sections yet (mid-republish-swap)", async () => {
    tableResults.briefs = { data: [{ id: "brief-1", issue_no: 204, status: "published" }], error: null };
    tableResults.sections = { data: [], error: null }; // the race: brief exists, sections not yet re-inserted

    const result = await fetchBriefByIssueNo(204);
    expect(result).toBeNull();
  });

  it("returns a payload when sections are present", async () => {
    tableResults.briefs = { data: [{ id: "brief-1", issue_no: 204, status: "published" }], error: null };
    tableResults.sections = {
      data: [
        {
          slug: "bb",
          ord: 1,
          title: "Bangladesh Bank",
          group_key: "banking",
          metrics: [],
          news: [],
          chart_series: [],
          chart_notes: [],
        },
      ],
      error: null,
    };

    const result = await fetchBriefByIssueNo(204);
    expect(result).not.toBeNull();
    expect(result!.sections).toHaveLength(1);
    expect(result!.sections[0].slug).toBe("bb");
  });
});

describe("fetchBriefByIssueNo — RLS posture (MED-7)", () => {
  it("always filters briefs on status=published — the only guard against serving a draft", async () => {
    tableResults.briefs = { data: [{ id: "brief-1", issue_no: 204, status: "published" }], error: null };
    tableResults.sections = {
      data: [{ slug: "bb", ord: 1, title: "x", group_key: "banking", metrics: [], news: [] }],
      error: null,
    };

    await fetchBriefByIssueNo(204);

    const eqCalls = recordedCalls.briefs.filter((c) => c.method === "eq");
    const statusFilter = eqCalls.find((c) => c.args[0] === "status");
    expect(statusFilter).toBeDefined();
    expect(statusFilter!.args[1]).toBe("published");
  });

  it("selects explicit columns on briefs, not select('*')", async () => {
    tableResults.briefs = { data: [{ id: "brief-1", issue_no: 204 }], error: null };
    tableResults.sections = { data: [{ slug: "bb", ord: 1, title: "x", group_key: "banking", metrics: [], news: [] }], error: null };

    await fetchBriefByIssueNo(204);

    const selectCall = recordedCalls.briefs.find((c) => c.method === "select");
    expect(selectCall).toBeDefined();
    expect(selectCall!.args[0]).not.toBe("*");
    // Strengthened (review round 2, optional): pin the EXACT column list,
    // not just "some string that isn't *" — drift here should fail loudly.
    expect(selectCall!.args[0]).toBe(__internals.BRIEF_SELECT);
  });
});

describe("fetchBriefByIssueNo — hostile / edge-case params", () => {
  it("returns null for a negative issue number (the query would just come back empty, not throw)", async () => {
    tableResults.briefs = { data: [], error: null };
    const result = await fetchBriefByIssueNo(-1);
    expect(result).toBeNull();
  });

  it("returns null for issue number 0", async () => {
    tableResults.briefs = { data: [], error: null };
    const result = await fetchBriefByIssueNo(0);
    expect(result).toBeNull();
  });

  it("returns null for NaN without throwing", async () => {
    tableResults.briefs = { data: [], error: null };
    await expect(fetchBriefByIssueNo(NaN)).resolves.toBeNull();
  });

  it("returns null when the briefs query itself errors", async () => {
    tableResults.briefs = { data: null, error: { message: "network error" } };
    const result = await fetchBriefByIssueNo(204);
    expect(result).toBeNull();
  });

  it("returns null when the sections query errors after a valid brief is found", async () => {
    tableResults.briefs = { data: [{ id: "brief-1", issue_no: 204 }], error: null };
    tableResults.sections = { data: null, error: { message: "network error" } };
    const result = await fetchBriefByIssueNo(204);
    expect(result).toBeNull();
  });
});
