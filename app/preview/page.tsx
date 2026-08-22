import { notFound } from "next/navigation";
import fs from "node:fs/promises";
import path from "node:path";
import type { Metadata } from "next";

import { ClientApp } from "@/app/components/ClientApp";
import type { BriefPayload } from "@/types/brief";

export const dynamic = "force-dynamic";

// /preview always renders fixture data, never a real issue — robots.txt
// disallows the path too, but a stale preview link (e.g. the 27-May
// dry-run fixture) sitting indexable with a live-looking "PREVIEW MODE"
// banner is worth a belt-and-braces noindex meta tag as well.
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

interface PageProps {
  searchParams: Promise<{ fixture?: string }>;
}

export default async function PreviewPage({ searchParams }: PageProps) {
  const { fixture } = await searchParams;
  if (!fixture) {
    return (
      <main style={{ padding: "2rem", fontFamily: "var(--mono, monospace)" }}>
        <h1>Preview mode</h1>
        <p>
          Append <code>?fixture=&lt;filename&gt;</code> to load a brief JSON from
          <code>public/fixtures/</code>.
        </p>
        <p>
          Example: <code>/preview?fixture=v1.4.0-dryrun-2026-05-28.json</code>
        </p>
      </main>
    );
  }

  // Allowlist filename — only .json files, no path traversal
  if (!/^[a-zA-Z0-9._-]+\.json$/.test(fixture)) {
    return notFound();
  }

  const fixturePath = path.join(process.cwd(), "public", "fixtures", fixture);
  let raw: string;
  try {
    raw = await fs.readFile(fixturePath, "utf-8");
  } catch {
    return notFound();
  }

  let payload: BriefPayload;
  try {
    payload = JSON.parse(raw) as BriefPayload;
  } catch {
    return notFound();
  }

  return <ClientApp brief={payload.brief} sections={payload.sections} preview />;
}
