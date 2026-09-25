import { describe, expect, it } from "vitest";
import { networkRateLimitKey } from "./ipRateLimitKey";

describe("networkRateLimitKey", () => {
  it.each([
    ["2001:db8::2", "2001:db8:0:0::/64"],
    ["2001:0DB8:0000:0000:0000:0000:0000:0008", "2001:db8:0:0::/64"],
    ["2001:db8:0:1::2", "2001:db8:0:1::/64"],
    ["2001:db8::192.0.2.8", "2001:db8:0:0::/64"],
    ["2001:db8:0:0:0:0:c000:208", "2001:db8:0:0::/64"],
    ["::1", "0:0:0:0::/64"],
    ["0:0:0:0:0:0:0:1", "0:0:0:0::/64"],
    ["::", "0:0:0:0::/64"],
    ["192.0.2.8", "192.0.2.8"],
    ["127.0.0.1", "127.0.0.1"],
    ["::ffff:192.0.2.8", "192.0.2.8"],
    ["0:0:0:0:0:FFFF:c000:0208", "192.0.2.8"],
  ])("normalizes %s to %s", (address, expected) => {
    expect(networkRateLimitKey(address)).toBe(expected);
  });

  it.each([
    "", "unknown", "not-an-ip", "2001:db8::1::2", "2001:db8:zz::1",
    "2001:db8:0:1:2:3:4", "1:2:3:4:5:6:7:8:9", "[::1]", "fe80::1%eth0",
    "256.0.0.1", "192.000.2.8", "::ffff:192.0.2.999", "192.0.2.8:443",
    "a".repeat(10_000),
  ])("bounds invalid address %s to the unknown bucket", (address) => {
    expect(networkRateLimitKey(address)).toBe("unknown");
  });
});
