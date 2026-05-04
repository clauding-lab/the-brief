import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Read env vars lazily so the module doesn't throw at build/prerender time
// when env is not yet wired (e.g. first Vercel build). Callers that actually
// need the client get a clear error.
function readConfig(): { url: string; key: string } {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase env vars. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (.env.local for dev, Vercel project env for deploys)."
    );
  }
  return { url, key };
}

export function createSupabaseClient(): SupabaseClient {
  const { url, key } = readConfig();
  return createClient(url, key, { auth: { persistSession: false } });
}

let _browserClient: SupabaseClient | null = null;
export function getBrowserSupabase(): SupabaseClient {
  if (!_browserClient) _browserClient = createSupabaseClient();
  return _browserClient;
}
