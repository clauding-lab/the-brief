import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

// Node runtime: needs server-only env (service-role key) and a module-level Map for
// the best-effort rate limiter (persists across invocations on a warm instance).
export const runtime = "nodejs";
// Never cache a mutating endpoint.
export const dynamic = "force-dynamic";

// ── Validation bounds ──────────────────────────────────────────────────────
const MAX_NAME = 120;
const MAX_ORG = 160;
const MAX_EMAIL = 254; // RFC 5321 practical maximum
// Pragmatic email shape check (not RFC-perfect). `[^\s@]` excludes whitespace and
// control chars, so the email field is inherently CRLF/header-injection safe. Not
// ReDoS-prone (single hard `@` delimiter, no ambiguous nested quantifiers).
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ── Rate limiting (best-effort, per serverless instance) ────────────────────
// Module-level state survives across requests on a warm Node instance but does NOT
// coordinate across the multiple instances Vercel may spin up (or cold starts), so
// this is a speed bump against naive scripted abuse, not a distributed-attack
// defense. A durable limiter (Upstash/Supabase RPC) is the real fix — future work.
const RATE_LIMIT_MAX = 5; // inserts
const RATE_LIMIT_WINDOW_MS = 60_000; // per minute per IP
const MAX_BUCKETS = 5000; // memory guard

type Bucket = { count: number; resetAt: number };
const buckets = new Map<string, Bucket>();

function isRateLimited(key: string, now: number): boolean {
  const bucket = buckets.get(key);
  if (!bucket || now > bucket.resetAt) {
    buckets.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }
  bucket.count += 1;
  return bucket.count > RATE_LIMIT_MAX;
}

function sweepBuckets(now: number): void {
  if (buckets.size <= MAX_BUCKETS) return;
  for (const [key, bucket] of buckets) {
    if (now > bucket.resetAt) buckets.delete(key);
  }
}

// Derive the rate-limit key from a TRUSTED source. On Vercel `x-real-ip` is set by the
// platform proxy and overwrites any client-supplied value; the LEFTMOST x-forwarded-for
// token is attacker-controlled (the platform appends the real IP to the right), so we
// never trust xff[0]. IPv6 is keyed by its /64 prefix so a single /64 allocation can't
// mint unlimited buckets.
function rateLimitKey(req: Request): string {
  const realIp = req.headers.get("x-real-ip");
  const xff = req.headers.get("x-forwarded-for");
  const ip = realIp?.trim() || xff?.split(",").pop()?.trim() || "unknown";
  if (ip.includes(":")) {
    return ip.split(":").slice(0, 4).join(":") + "::/64"; // IPv6 /64
  }
  return ip;
}

function fieldStr(source: Record<string, unknown>, key: string): string {
  const v = source[key];
  return typeof v === "string" ? v.trim() : "";
}

// Strip control chars — C0 (code < 0x20) and DEL (0x7F) — that could enable header/body
// injection once the row is emailed via Brevo (one POST per recipient), then collapse
// internal whitespace. Code-point filter (no control-char regex literal, no ReDoS).
function sanitizeField(s: string): string {
  let out = "";
  for (const ch of s) {
    const code = ch.codePointAt(0) ?? 0;
    out += code < 0x20 || code === 0x7f ? " " : ch;
  }
  return out.replace(/\s+/g, " ").trim();
}

function json(body: unknown, status: number): NextResponse {
  return NextResponse.json(body, {
    status,
    headers: { "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store" },
  });
}

export async function POST(req: Request): Promise<NextResponse> {
  const now = Date.now();
  sweepBuckets(now);

  if (isRateLimited(rateLimitKey(req), now)) {
    return json({ ok: false, error: "Too many requests. Please try again shortly." }, 429);
  }

  // Only accept JSON, and same-origin (blocks cross-origin / simple-request CSRF-style
  // submissions from other sites). The form POSTs application/json from same origin.
  if (!(req.headers.get("content-type") || "").includes("application/json")) {
    return json({ ok: false, error: "Invalid request." }, 415);
  }
  const origin = req.headers.get("origin");
  if (origin) {
    const host = req.headers.get("host");
    try {
      if (host && new URL(origin).host !== host) {
        return json({ ok: false, error: "Forbidden." }, 403);
      }
    } catch {
      return json({ ok: false, error: "Forbidden." }, 403);
    }
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json({ ok: false, error: "Invalid request." }, 400);
  }
  if (typeof body !== "object" || body === null) {
    return json({ ok: false, error: "Invalid request." }, 400);
  }
  const fields = body as Record<string, unknown>;

  // Honeypot: `company_website` is hidden from humans (off-screen in the form). A bot
  // that auto-fills it reveals itself — return success WITHOUT inserting, so it gets
  // no signal that it was caught.
  if (fieldStr(fields, "company_website")) {
    return json({ ok: true }, 200);
  }

  const name = sanitizeField(fieldStr(fields, "name"));
  // Email goes through sanitizeField too (review LOW): EMAIL_RE's [^\s@] rejects
  // whitespace but NOT non-whitespace control bytes (0x00-0x08, 0x0e-0x1f, 0x7f),
  // which could otherwise enter the stored value. Sanitizing maps them to spaces,
  // which the regex then rejects — a control-byte email fails validation cleanly.
  const email = sanitizeField(fieldStr(fields, "email"));
  const organisation = sanitizeField(fieldStr(fields, "organisation"));

  if (!name || name.length > MAX_NAME) {
    return json({ ok: false, error: "A valid name is required." }, 400);
  }
  if (!email || email.length > MAX_EMAIL || !EMAIL_RE.test(email)) {
    return json({ ok: false, error: "A valid email address is required." }, 400);
  }
  if (organisation.length > MAX_ORG) {
    return json({ ok: false, error: "Organisation is too long." }, 400);
  }

  const url = process.env.SUPABASE_URL ?? process.env.NEXT_PUBLIC_SUPABASE_URL;
  // Prefer the service-role key so this route is the ONLY insert path (service_role
  // bypasses RLS). Verified against pg_policy on 2026-07-09: SUPABASE_SERVICE_ROLE_KEY
  // is set in Vercel AND the anon INSERT policy on `subscribers` has been dropped (0
  // policies, RLS on) — so the `NEXT_PUBLIC_SUPABASE_ANON_KEY` fallback below is dead
  // in production; it would 502 on RLS if it were ever reached. It stays only as a
  // local-dev fallback for a checkout without SUPABASE_SERVICE_ROLE_KEY set.
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const key = serviceKey ?? process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    console.error("subscribe route: missing Supabase URL/key env");
    return json({ ok: false, error: "Subscription is temporarily unavailable." }, 503);
  }
  if (!serviceKey) {
    console.warn(
      "subscribe route: SUPABASE_SERVICE_ROLE_KEY not set — falling back to the public " +
        "anon key, which has no INSERT policy on `subscribers` in production; inserts will fail RLS (502)",
    );
  }

  const supabase = createClient(url, key, { auth: { persistSession: false } });
  const { error } = await supabase
    .from("subscribers")
    .insert([{ name, email, organisation: organisation || null }]);

  if (error) {
    // Log the error CODE only, never the message (review LOW): a unique-violation
    // message embeds the subscriber's email — PII in Vercel logs on a product that
    // pitches "we don't track". The code (e.g. 23505) is enough to diagnose.
    console.error("subscribe route: insert failed, code:", error.code ?? "unknown");
    return json({ ok: false, error: "Could not subscribe. Please try again." }, 502);
  }

  return json({ ok: true }, 200);
}
