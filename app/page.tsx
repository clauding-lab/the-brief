import { createClient } from "@supabase/supabase-js";
import type { BriefPayload } from "@/types/brief";
import { STATIC_FALLBACK } from "@/lib/staticFallback";
import { ClientApp } from "./components/ClientApp";

// Re-fetch every 60s on the server. Subscribe form mutates `subscribers`, not the
// brief, so this cache is safe for editorial content.
export const revalidate = 60;

async function fetchInitialBrief(): Promise<BriefPayload> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return STATIC_FALLBACK;

  // Bypass Next.js fetch Data Cache so the RPC re-runs on every page regeneration.
  // Otherwise a freshly-published brief stays invisible until the fetch cache TTL
  // expires, which Vercel was capping at ~5 minutes regardless of `revalidate`.
  const sb = createClient(url, key, {
    auth: { persistSession: false },
    global: {
      fetch: (input, init) => fetch(input, { ...init, cache: "no-store" }),
    },
  });
  const { data, error } = await sb.rpc("get_latest_brief");
  if (error || !data?.brief) return STATIC_FALLBACK;
  return { ...(data as BriefPayload), _source: "live", _fetchedAt: Date.now() };
}

export default async function Home() {
  const initialData = await fetchInitialBrief();
  return <ClientApp initialData={initialData} />;
}
