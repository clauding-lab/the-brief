import { isIP } from "node:net";

/** Stable network bucket for a validated address; header trust belongs to the caller. */
export function networkRateLimitKey(address: string): string {
  // Proxy addresses are unscoped, bare IPs. Bound malformed input to one bucket.
  if (address.length > 45 || address.includes("%")) return "unknown";
  const family = isIP(address);
  if (family === 4) return address;
  if (family !== 6) return "unknown";

  // The platform validator checked syntax. Convert an IPv4 tail into two hextets
  // (16-bit groups), then expand the single compressed zero run to eight groups.
  let hexAddress = address;
  if (address.includes(".")) {
    const tailStart = address.lastIndexOf(":") + 1;
    const octets = address.slice(tailStart).split(".").map(Number);
    hexAddress = address.slice(0, tailStart) +
      ((octets[0] << 8) | octets[1]).toString(16) + ":" +
      ((octets[2] << 8) | octets[3]).toString(16);
  }
  const [left, right] = hexAddress.split("::");
  const head = left ? left.split(":") : [];
  const tail = right ? right.split(":") : [];
  const groups = (right === undefined ? head : [
    ...head, ...Array<string>(8 - head.length - tail.length).fill("0"), ...tail,
  ]).map((group) => parseInt(group, 16));

  // IPv4-mapped IPv6 is the same client as its dotted IPv4 representation.
  if (groups.slice(0, 5).every((group) => group === 0) && groups[5] === 0xffff) {
    return [groups[6] >> 8, groups[6] & 255, groups[7] >> 8, groups[7] & 255].join(".");
  }
  return groups.slice(0, 4).map((group) => group.toString(16)).join(":") + "::/64";
}
