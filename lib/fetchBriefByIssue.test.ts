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

// Every from(table) call is one PostgREST request (R3c counts them).
const fromCalls: string[] = [];

vi.mock("@supabase/supabase-js", () => ({
  createClient: vi.fn(() => ({
    from: vi.fn((table: string) => {
      fromCalls.push(table);
      return makeChain(table);
    }),
  })),
}));

// Imported AFTER the mock is registered (vi.mock is hoisted by Vitest, so
// this ordering is safe regardless of where the import statement sits).
import { fetchBriefByIssueNo, __internals } from "./fetchBriefByIssue";

beforeEach(() => {
  fromCalls.length = 0;
  recordedCalls.briefs = [];
  recordedCalls.sections = [];
  tableResults.briefs = { data: [], error: null };
  tableResults.sections = { data: [], error: null };
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test-anon-key");
});

describe("fetchBriefByIssueNo — landmine 33 (same-day republish race)", () => {
  it("returns null when the briefs row exists but has zero sections yet (mid-republish-swap)", async () => {
    // The header row carries its sections in the same response (R3c); an
    // issue with zero sections is never rendered as an empty edition.
    tableResults.briefs = {
      data: [{ id: "brief-1", issue_no: 204, status: "published", sections: [] }],
      error: null,
    };

    const result = await fetchBriefByIssueNo(204);
    expect(result).toBeNull();
  });

  it("returns a payload when sections are present", async () => {
    tableResults.briefs = {
      data: [
        {
          id: "brief-1",
          issue_no: 204,
          status: "published",
          sections: [
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
    tableResults.briefs = {
      data: [
        {
          id: "brief-1",
          issue_no: 204,
          status: "published",
          sections: [{ slug: "bb", ord: 1, title: "x", group_key: "banking", metrics: [], news: [] }],
        },
      ],
      error: null,
    };

    await fetchBriefByIssueNo(204);

    const eqCalls = recordedCalls.briefs.filter((c) => c.method === "eq");
    const statusFilter = eqCalls.find((c) => c.args[0] === "status");
    expect(statusFilter).toBeDefined();
    expect(statusFilter!.args[1]).toBe("published");
  });

  it("selects explicit columns on briefs, not select('*')", async () => {
    tableResults.briefs = {
      data: [
        {
          id: "brief-1",
          issue_no: 204,
          sections: [{ slug: "bb", ord: 1, title: "x", group_key: "banking", metrics: [], news: [] }],
        },
      ],
      error: null,
    };

    await fetchBriefByIssueNo(204);

    const selectCall = recordedCalls.briefs.find((c) => c.method === "select");
    expect(selectCall).toBeDefined();
    expect(selectCall!.args[0]).not.toBe("*");
    // Strengthened (review round 2, optional): pin the EXACT column list,
    // not just "some string that isn't *" — drift here should fail loudly.
    // R3c: the same request nests the sections, so the header list is its prefix.
    expect(selectCall!.args[0]).toBe(
      `${__internals.BRIEF_SELECT},sections(${__internals.SECTION_SELECT})`,
    );
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
    // R3c: sections arrive inside the header row; a missing/null embed is the
    // one-request form of "the content read failed".
    tableResults.briefs = { data: [{ id: "brief-1", issue_no: 204, sections: null }], error: null };
    const result = await fetchBriefByIssueNo(204);
    expect(result).toBeNull();
  });
});

// R3c (design test 7, unit level): a same-day correction commits inside one
// database transaction and keeps the parent UUID. Two HTTP requests (header,
// then sections) could still pair the OLD header with the NEW sections if a
// publication commits between them — so a permalink must be ONE request.
// All rows below are SYNTHETIC.
function nestedIssue(sections: unknown[]) {
  return {
    id: "brief-1",
    issue_no: 236,
    volume: 1,
    brief_date: "2026-09-29",
    read_minutes: 9,
    cover_metric: null,
    published_at: "2026-09-29T02:05:00+00:00",
    status: "published",
    todays_call: "SYNTHETIC call",
    lens: null,
    frame: null,
    sections,
  };
}

describe("fetchBriefByIssueNo — one snapshot (R3c)", () => {
  it("reads the header and every section with its children in ONE request rooted at briefs", async () => {
    tableResults.briefs = { data: [nestedIssue([{ slug: "bb", ord: 1, title: "x", group_key: "banking" }])], error: null };

    await fetchBriefByIssueNo(236);

    expect(fromCalls).toEqual(["briefs"]);
    const selects = recordedCalls.briefs.filter((c) => c.method === "select");
    expect(selects).toHaveLength(1);
    const select = String(selects[0].args[0]);
    for (const child of ["sections(", "metrics(", "news(", "chart_series(", "chart_notes("]) {
      expect(select).toContain(child);
    }
    expect(recordedCalls.sections).toEqual([]);
  });

  it("orders sections and every ordinal child on the server, with a deterministic tie-breaker", async () => {
    tableResults.briefs = { data: [nestedIssue([{ slug: "bb", ord: 1, title: "x", group_key: "banking" }])], error: null };

    await fetchBriefByIssueNo(236);

    const orders = recordedCalls.briefs
      .filter((c) => c.method === "order")
      .map((c) => `${(c.args[1] as { referencedTable?: string })?.referencedTable}:${c.args[0]}`);
    expect(orders).toEqual([
      "sections:ord",
      "sections:id",
      "sections.metrics:ord",
      "sections.metrics:id",
      "sections.news:ord",
      "sections.news:id",
      "sections.chart_series:ts",
      "sections.chart_series:series_key",
      "sections.chart_notes:ts",
      "sections.chart_notes:series_key",
      "sections.chart_notes:id",
    ]);
  });

  it("keeps the permalink payload shape: header without the nested key, adapted sections", async () => {
    tableResults.briefs = {
      data: [
        nestedIssue([
          {
            slug: "bb",
            ord: 2,
            title: "Bangladesh Bank",
            group_key: "banking",
            metrics: [
              { label: "second", value: "2", ord: 1 },
              { label: "first", value: "1", ord: 0 },
            ],
            news: [{ headline: "only", source: "SYNTHETIC", ord: 0 }],
            chart_series: [{ series_key: null, ts: "2026-09-28", value: 1.5 }],
            chart_notes: [{ series_key: "bb", ts: "2026-09-28", label: "note", detail: null }],
          },
          { slug: "fx", ord: 3, title: "Empty", group_key: "markets", metrics: [], news: [], chart_series: [], chart_notes: [] },
        ]),
      ],
      error: null,
    };

    const result = await fetchBriefByIssueNo(236);

    expect(result).not.toBeNull();
    expect(result!.brief).not.toHaveProperty("sections");
    expect(result!.brief).toMatchObject({ id: "brief-1", issue_no: 236, todays_call: "SYNTHETIC call" });
    expect(result!.sections.map((s) => s.slug)).toEqual(["bb", "fx"]);
    const bb = result!.sections[0];
    expect(bb.metrics).toEqual([
      { label: "first", value: "1" },
      { label: "second", value: "2" },
    ]);
    expect(bb.series).toEqual([{ key: undefined, ts: "2026-09-28", value: 1.5 }]);
    expect(bb.notes).toEqual([{ series_key: "bb", ts: "2026-09-28", label: "note", detail: undefined }]);
    // A legitimately empty section keeps empty arrays, never undefined/null.
    const fx = result!.sections[1];
    expect([fx.metrics, fx.news, fx.series, fx.notes]).toEqual([[], [], [], []]);
  });
});
