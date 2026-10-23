import { beforeEach, describe, expect, it, vi } from "vitest";

const insert = vi.hoisted(() => vi.fn().mockResolvedValue({ error: null }));
vi.mock("@supabase/supabase-js", () => ({
  createClient: () => ({ from: () => ({ insert }) }),
}));

let post: typeof import("./route").POST;

function request(headers: Record<string, string>) {
  return new Request("https://brief.example/api/subscribe", {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify({ name: "Reader", email: "reader@example.test" }),
  });
}

beforeEach(async () => {
  vi.resetModules();
  insert.mockClear();
  vi.stubEnv("SUPABASE_URL", "https://example.supabase.co");
  vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "test-key");
  post = (await import("./route")).POST;
});

describe("signup network limiting", () => {
  it("blocks request six across hosts and spellings in one IPv6 /64", async () => {
    const hosts = ["2001:db8::1", "2001:db8::2", "2001:0db8:0:0::3",
      "2001:db8:0000:0000::4", "2001:DB8:0:0:0:0:0:5", "2001:db8::192.0.2.6"];
    for (const [i, ip] of hosts.entries()) {
      expect((await post(request({ "x-real-ip": ip }))).status).toBe(i < 5 ? 200 : 429);
    }
    expect(insert).toHaveBeenCalledTimes(5);
    expect((await post(request({ "x-real-ip": "2001:db8:0:1::1" }))).status).toBe(200);
  });

  it("shares native IPv4 and IPv4-mapped IPv6 counters", async () => {
    for (let i = 0; i < 5; i++) {
      expect((await post(request({ "x-real-ip": "192.0.2.8" }))).status).toBe(200);
    }
    expect((await post(request({ "x-real-ip": "::ffff:c000:208" }))).status).toBe(429);
    expect((await post(request({ "x-real-ip": "192.0.2.9" }))).status).toBe(200);
  });

  it("shares one bucket for missing and invalid input", async () => {
    for (let i = 0; i < 5; i++) {
      expect((await post(request({ "x-real-ip": `invalid-${i}` }))).status).toBe(200);
    }
    expect((await post(request({}))).status).toBe(429);
  });

  it("still trusts x-real-ip ahead of all forwarded-for tokens", async () => {
    for (let i = 0; i < 6; i++) {
      expect((await post(request({
        "x-real-ip": "192.0.2.10",
        "x-forwarded-for": `198.51.100.${i}, 203.0.113.${i}`,
      }))).status).toBe(i < 5 ? 200 : 429);
    }
  });

  it("still uses the last forwarded-for token when x-real-ip is absent", async () => {
    for (let i = 0; i < 6; i++) {
      expect((await post(request({
        "x-forwarded-for": `198.51.100.${i}, 203.0.113.10`,
      }))).status).toBe(i < 5 ? 200 : 429);
    }
  });

  it("expires a network counter after the one-minute window", async () => {
    const clock = vi.spyOn(Date, "now").mockReturnValue(1_000);
    try {
      for (let i = 0; i < 6; i++) await post(request({ "x-real-ip": "::1" }));
      clock.mockReturnValue(61_001);
      expect((await post(request({ "x-real-ip": "::1" }))).status).toBe(200);
    } finally {
      clock.mockRestore();
    }
  });
});

// Both runtimes consume this storage-boundary contract; Python must accept every
// exact stored value this real route emits, not just a similar regex example.
import emailContract from "../../../tests/fixtures/subscriber_email_contract.json";

describe("subscriber email storage contract", () => {
  it.each(emailContract.accepted)("stores the shared canonical value for $raw", async ({ raw, stored }) => {
    const req = new Request("https://brief.example/api/subscribe", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "Reader", email: raw }),
    });
    expect((await post(req)).status).toBe(200);
    expect(insert.mock.calls[0][0][0].email).toBe(stored);
  });

  it.each(emailContract.rejected)("rejects incompatible address %j before storage", async (email) => {
    const req = new Request("https://brief.example/api/subscribe", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: "Reader", email }),
    });
    expect((await post(req)).status).toBe(400);
    expect(insert).not.toHaveBeenCalled();
  });
});
