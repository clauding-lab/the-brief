"use client";

import { useState } from "react";
import { Hair } from "./Hair";

interface SubscribeCTAProps {
  volume?: number | null;
  issueNo?: number | null;
}

export function SubscribeCTA({ volume, issueNo }: SubscribeCTAProps = {}) {
  const volLabel = `Vol. ${String(volume ?? 1).padStart(2, "0")}`;
  const issueLabel = `Issue ${issueNo ?? 87}`;
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [email, setEmail] = useState("");
  // Honeypot: hidden from humans, tempting to bots. Real users leave it empty.
  const [companyWebsite, setCompanyWebsite] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmedName = name.trim();
    const trimmedEmail = email.trim();
    if (!trimmedName || !trimmedEmail) {
      setErr("Name and email required.");
      return;
    }
    // Lightweight client-side format check for fast feedback; the server route at
    // /api/subscribe is the authoritative validator (+ rate limit + honeypot).
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setErr("Enter a valid email address.");
      return;
    }
    setSubmitting(true);
    setErr(null);
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: trimmedName,
          organisation: org.trim(),
          email: trimmedEmail,
          company_website: companyWebsite,
        }),
      });
      const data = (await res.json().catch(() => null)) as
        | { ok?: boolean; error?: string }
        | null;
      if (!res.ok || !data?.ok) {
        throw new Error(data?.error || "Could not subscribe. Try again.");
      }
      setDone(true);
      setName("");
      setOrg("");
      setEmail("");
    } catch (ex: unknown) {
      const msg = ex instanceof Error ? ex.message : "Could not subscribe. Try again.";
      setErr(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="tb-cta" id="subscribe" aria-label="Subscribe">
      <div className="tb-cta-dark">
        <div className="eyebrow">Subscribe</div>
        <div>
          <div className="head">
            One brief.<br />
            Every morning.<br />
            <span className="accent">Free.</span>
          </div>
          <div className="body">
            What treasury, policy and corporate-finance desks across Dhaka start
            their day with. 08:00 BDT sharp. No filler.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            gap: 16,
            alignItems: "center",
            fontSize: 10.5,
            color: "rgba(244,239,230,0.6)",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          <span>{volLabel}</span>
          <span style={{ width: 18, height: 1, background: "rgba(244,239,230,0.3)" }} />
          <span>{issueLabel}</span>
        </div>
      </div>

      <form className="tb-cta-form" onSubmit={handleSubmit} noValidate>
        <div className="eyebrow">Daily, 08:00 BDT</div>
        <Hair />
        {done ? (
          <div style={{ paddingTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ fontSize: 22, fontWeight: 300, letterSpacing: "-0.01em" }}>
              You&rsquo;re on the list.
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--ink-2)",
                maxWidth: 360,
                lineHeight: 1.5,
              }}
            >
              First brief lands in your inbox tomorrow at 08:00 BDT. Forward freely; we
              don&rsquo;t track opens.
            </div>
          </div>
        ) : (
          <>
            <label>
              <span className="lbl">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Mehrin Rahman"
                required
              />
            </label>
            <label>
              <span className="lbl">Organisation</span>
              <input
                value={org}
                onChange={(e) => setOrg(e.target.value)}
                placeholder="BRAC Bank · Treasury"
              />
            </label>
            <label>
              <span className="lbl">Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="m.rahman@bracbank.com"
                required
              />
            </label>
            {/* Honeypot — visually hidden, off-screen, skipped by AT and tab order.
                Real users never see or fill it; bots that auto-fill get silently dropped. */}
            <div
              aria-hidden="true"
              style={{
                position: "absolute",
                left: "-9999px",
                width: 1,
                height: 1,
                overflow: "hidden",
              }}
            >
              <label>
                Company website
                <input
                  type="text"
                  name="company_website"
                  tabIndex={-1}
                  autoComplete="off"
                  value={companyWebsite}
                  onChange={(e) => setCompanyWebsite(e.target.value)}
                />
              </label>
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                marginTop: 10,
              }}
            >
              <button className="tb-btn-submit" type="submit" disabled={submitting}>
                {submitting ? "Sending …" : "Receive the brief →"}
              </button>
              <span className="tb-cta-helper">
                No tracking. No marketing. Unsubscribe anytime — one email.
              </span>
            </div>
            {err && <div style={{ color: "var(--bear)", fontSize: 12 }}>{err}</div>}
          </>
        )}
      </form>
    </section>
  );
}
