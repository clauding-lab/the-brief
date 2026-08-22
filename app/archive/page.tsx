import type { Metadata } from "next";
import Link from "next/link";

import { fetchArchiveIndex } from "@/lib/fetchBriefByIssue";
import { formatBriefDate } from "@/lib/format";

export const metadata: Metadata = {
  title: "Archive · The Brief",
  description: "Every published issue of The Brief, Bangladesh's daily banking-desk macro read.",
  alternates: { canonical: "/archive" },
};

// First sentence of `todays_call` — a short, honest preview of the issue's
// thesis rather than the whole paragraph.
function firstLine(text: string | null): string {
  if (!text) return "";
  const m = text.match(/^.*?[.!?](?=\s|$)/);
  return (m ? m[0] : text).trim();
}

export default async function ArchivePage() {
  const issues = await fetchArchiveIndex();

  return (
    <main className="tb-body">
      <h1 className="tb-archive-title">Archive</h1>
      <p className="tb-archive-sub">
        {issues.length} published {issues.length === 1 ? "issue" : "issues"}, newest first.{" "}
        <Link href="/">Back to today&rsquo;s issue →</Link>
      </p>
      <ul className="tb-archive-list">
        {issues.map((issue) => (
          <li key={issue.issue_no} className="tb-archive-row">
            <Link href={`/issue/${issue.issue_no}`}>
              <span className="tb-archive-no">No. {String(issue.issue_no).padStart(3, "0")}</span>
              <span className="tb-archive-date">{formatBriefDate(issue.brief_date)}</span>
              <span className="tb-archive-call">{firstLine(issue.todays_call)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
