import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { ClientApp } from "@/app/components/ClientApp";
import { fetchBriefByIssueNo } from "@/lib/fetchBriefByIssue";

interface PageProps {
  params: Promise<{ no: string }>;
}

function parseIssueNo(no: string): number | null {
  if (!/^\d+$/.test(no)) return null;
  const n = Number(no);
  return n > 0 ? n : null;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { no } = await params;
  const issueNo = parseIssueNo(no);
  if (issueNo === null) return {};

  const payload = await fetchBriefByIssueNo(issueNo);
  if (!payload) return {};

  const title = `The Brief · Issue No. ${payload.brief.issue_no} · ${payload.brief.brief_date}`;
  const description = payload.brief.todays_call?.slice(0, 155);
  return {
    title,
    description,
    alternates: { canonical: `/issue/${issueNo}` },
    openGraph: { title, description },
  };
}

export default async function IssuePage({ params }: PageProps) {
  const { no } = await params;
  const issueNo = parseIssueNo(no);
  if (issueNo === null) notFound();

  // Canonicalize leading zeros (review round 1, LOW): /issue/0204 and
  // /issue/204 are the same issue, but two URLs for it split link equity
  // and let an indexer treat them as duplicate content.
  const canonical = String(issueNo);
  if (no !== canonical) redirect(`/issue/${canonical}`);

  const payload = await fetchBriefByIssueNo(issueNo);
  if (!payload) notFound();

  // `historical` stops ClientApp's mount-time refetch, which otherwise
  // swaps this fixed issue for today's latest brief a moment after load —
  // the whole point of a permalink is that it doesn't do that.
  return <ClientApp brief={payload.brief} sections={payload.sections} historical />;
}
